import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from planlabel.deciders.openrouter import OPENROUTER_DECISIONS_URL, OpenRouterDecider
from planlabel.deciders.questions import QUESTIONS
from planlabel.models import Category, Subcategory
from planlabel.usage import UTC_ZONE, QuotaTracker
from tests.conftest import make_application

MODEL = "typesafe/jev-1.14"


@pytest.fixture
def real(fixtures_dir):
    data = json.loads((fixtures_dir / "openrouter" / "jev_decision_wind.json").read_text())
    return data["response"]


def decider(tmp_db, *, key="k", model=MODEL, rpm=0, rpd=0, now=None):
    now = now or datetime(2026, 11, 19, 23, 30, tzinfo=UTC)
    tracker = QuotaTracker(tmp_db, model, tz=UTC_ZONE, rpm=rpm, rpd=rpd, clock=lambda: now)
    return OpenRouterDecider(
        slot=2, model=model, api_key=key, client=httpx.Client(), tracker=tracker, timeout_s=10
    )


@respx.mock
def test_O01_request_shape(tmp_db, real):
    route = respx.post(OPENROUTER_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    decider(tmp_db, key="segredo").decide(make_application(description="7 turbines"))
    req = route.calls.last.request
    body = json.loads(req.content)
    assert req.headers["authorization"] == "Bearer segredo"
    assert body == {"model": MODEL, "state": "7 turbines", "questions": QUESTIONS}
    for header in ("http-referer", "x-title"):
        assert header not in req.headers


@respx.mock
def test_O02_real_response_and_snapshot_model_name(tmp_db, real):
    respx.post(OPENROUTER_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    result = decider(tmp_db).decide(make_application())
    assert result.reason == "ok"
    assert result.model == "typesafe/jev-1.14-20261014"
    assert result.decision.model == "typesafe/jev-1.14-20261014"
    assert (result.decision.subcategory, result.decision.subcategory_pct) == (Subcategory.WIND, 100)
    assert (result.decision.category, result.decision.category_pct) == (Category.ENERGY, 100)


@pytest.mark.parametrize(
    "body",
    [
        {"answers": {"subcategory": {"type": "refusal"}, "category": {"type": "refusal"}}},
        {"answers": {}},
        {"error": {"message": "x", "code": 400}},
    ],
)
@respx.mock
def test_O03_refusal_missing_or_error_body(tmp_db, body):
    respx.post(OPENROUTER_DECISIONS_URL).mock(return_value=httpx.Response(200, json=body))
    result = decider(tmp_db).decide(make_application())
    assert (result.decision, result.reason) == (None, "error")


@pytest.mark.parametrize(
    ("mock", "reason"),
    [
        ({"return_value": httpx.Response(429)}, "rate_limited"),
        ({"return_value": httpx.Response(402, json={"error": {"code": 402}})}, "error"),
        ({"return_value": httpx.Response(503)}, "error"),
        ({"side_effect": httpx.ConnectTimeout("lento")}, "error"),
    ],
)
@respx.mock
def test_O04_http_errors_no_retry(tmp_db, mock, reason):
    route = respx.post(OPENROUTER_DECISIONS_URL).mock(**mock)
    assert decider(tmp_db).decide(make_application()).reason == reason
    assert route.call_count == 1


@respx.mock
def test_O05_without_key_and_alias_rejected(tmp_db):
    route = respx.post(OPENROUTER_DECISIONS_URL)
    result = decider(tmp_db, key=None).decide(make_application())
    assert (result.reason, result.model) == ("no_key", MODEL)
    assert route.call_count == 0
    with pytest.raises(ValueError, match="versão fixa"):
        decider(tmp_db, model="~typesafe/jev-latest")


@respx.mock
def test_O06_usage_counted_per_utc_day_and_optional_limit(tmp_db, real):
    respx.post(OPENROUTER_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    d = decider(tmp_db)
    for n in range(3):
        assert d.decide(make_application(description=f"t{n}")).reason == "ok"
    u = tmp_db.usage("2026-11-19", MODEL)  # 23:30 UTC ainda é dia 19 em UTC
    assert u.requests == 3
    assert u.tokens == 3 * (real["usage"]["input_tokens"] + real["usage"]["output_tokens"])
    limited = decider(tmp_db, rpd=3)
    assert limited.decide(make_application(description="t9")).reason == "quota_exhausted"
