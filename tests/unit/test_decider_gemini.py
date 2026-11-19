import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from planlabel.deciders.gemini import GEMINI_DECISIONS_URL, GeminiDecider
from planlabel.deciders.questions import QUESTIONS
from planlabel.models import Category, Subcategory
from planlabel.usage import QuotaTracker, next_reset, quota_day
from tests.conftest import SUBS, make_application

SNAPSHOT = "snapshots/decision_questions.json"


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def real(fixtures_dir):
    return json.loads((fixtures_dir / "gemini" / "decision_wind_valid.json").read_text())[
        "response"
    ]


def decider(tmp_db, *, key="k", model="gemini-decision-1", clock=None, rpm=200, rpd=10000):
    clock = clock or Clock(datetime(2026, 11, 19, 12, tzinfo=UTC))
    tracker = QuotaTracker(tmp_db, model, rpm=rpm, rpd=rpd, clock=clock)
    return GeminiDecider(
        slot=1, model=model, api_key=key, client=httpx.Client(), tracker=tracker, timeout_s=10
    )


def answers(sub="wind", cat="energy"):
    probs = dict.fromkeys(SUBS, 0.0)
    probs[sub] = 1.0
    cprobs = {"energy": 0.0, "not_energy": 0.0}
    cprobs[cat] = 1.0
    return {
        "answers": {
            "subcategory": {
                "type": "choice",
                "choice": sub,
                "probabilities": probs,
                "confidence": 1,
            },
            "category": {"type": "choice", "choice": cat, "probabilities": cprobs, "confidence": 1},
        },
        "usage": {"total_tokens": 600, "total_input_tokens": 600, "total_output_tokens": 0},
    }


@respx.mock
def test_G01_request_shape(tmp_db, real):
    route = respx.post(GEMINI_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    app = make_application(description="7 no. wind turbines")
    decider(tmp_db, key="segredo").decide(app)
    req = route.calls.last.request
    body = json.loads(req.content)
    assert req.headers["x-goog-api-key"] == "segredo"
    assert body["model"] == "gemini-decision-1"
    assert body["input"] == "7 no. wind turbines"
    assert set(body["questions"]) == {"subcategory", "category"}
    assert body["questions"]["subcategory"]["type"] == "choice"
    assert list(body["questions"]["subcategory"]["criteria"]) == SUBS
    assert list(body["questions"]["category"]["criteria"]) == ["energy", "not_energy"]


@respx.mock
def test_G02_real_response_becomes_decision(tmp_db, real):
    respx.post(GEMINI_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    result = decider(tmp_db).decide(make_application())
    d = result.decision
    assert result.reason == "ok"
    assert result.model == "gemini-decision-1"
    assert d.subcategory == Subcategory.WIND
    assert d.subcategory_pct == 99
    assert d.category == Category.ENERGY
    assert d.category_pct == 100
    assert d.consistent is True
    assert sum(d.subcategory_distribution.values()) == 100


@respx.mock
def test_G03_contradictory_answer_is_valid(tmp_db):
    respx.post(GEMINI_DECISIONS_URL).mock(
        return_value=httpx.Response(200, json=answers("wind", "not_energy"))
    )
    d = decider(tmp_db).decide(make_application()).decision
    assert d.consistent is False
    assert (d.subcategory, d.category) == (Subcategory.WIND, Category.NOT_ENERGY)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="não é json"),
        httpx.Response(200, json={"answers": {"subcategory": answers()["answers"]["subcategory"]}}),
        httpx.Response(
            200, json={"answers": {**answers()["answers"], "category": {"type": "refusal"}}}
        ),
        httpx.Response(
            200,
            json={
                "answers": {
                    **answers()["answers"],
                    "category": {
                        "type": "choice",
                        "choice": "energy",
                        "probabilities": {"energy": 0.5, "not_energy": 0.1},
                    },
                }
            },
        ),
        httpx.Response(400, json={"error": {"code": "safety", "message": "blocked"}}),
    ],
)
@respx.mock
def test_G04_invalid_answers_are_error_not_exception(tmp_db, response):
    respx.post(GEMINI_DECISIONS_URL).mock(return_value=response)
    result = decider(tmp_db).decide(make_application())
    assert (result.decision, result.reason) == (None, "error")


@pytest.mark.parametrize(
    ("mock", "reason"),
    [
        ({"return_value": httpx.Response(429)}, "rate_limited"),
        ({"return_value": httpx.Response(500)}, "error"),
        ({"side_effect": httpx.ReadTimeout("lento")}, "error"),
    ],
)
@respx.mock
def test_G05_http_errors_and_no_retry(tmp_db, mock, reason):
    route = respx.post(GEMINI_DECISIONS_URL).mock(**mock)
    result = decider(tmp_db).decide(make_application())
    assert result.reason == reason
    assert route.call_count == 1


@respx.mock
def test_G06_cache_same_description_one_call(tmp_db, real):
    route = respx.post(GEMINI_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    d = decider(tmp_db)
    d.decide(make_application("abp", 1, description="same text"))
    d.decide(make_application("eplanning", 2, description="same text"))
    assert route.call_count == 1


def test_G07_questions_snapshot(fixtures_dir):
    path = fixtures_dir / SNAPSHOT
    assert json.loads(path.read_text()) == QUESTIONS, (
        "As perguntas aos modelos mudaram. Se foi de propósito, regrave o snapshot "
        f"({SNAPSHOT}) e explique no commit."
    )
    text = json.dumps(QUESTIONS)
    for sub in SUBS:
        assert sub in QUESTIONS["subcategory"]["criteria"]
    assert "turbines" in text
    assert "ground-mounted" in text


@respx.mock
def test_G08_without_key_no_call(tmp_db):
    route = respx.post(GEMINI_DECISIONS_URL)
    result = decider(tmp_db, key="").decide(make_application())
    assert (result.reason, result.model, result.decision) == ("no_key", "gemini-decision-1", None)
    assert route.call_count == 0


@respx.mock
def test_G08_model_id_goes_in_body(tmp_db, real):
    route = respx.post(GEMINI_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    decider(tmp_db, model="gemini-decision-2").decide(make_application())
    assert json.loads(route.calls.last.request.content)["model"] == "gemini-decision-2"


@respx.mock
def test_G09_every_sent_request_counts_cache_does_not(tmp_db, real):
    respx.post(GEMINI_DECISIONS_URL).mock(
        side_effect=[
            httpx.Response(200, json=real),
            httpx.Response(429),
            httpx.Response(500),
            httpx.ReadTimeout("lento"),
        ]
    )
    d = decider(tmp_db)
    for n in range(4):
        d.decide(make_application(description=f"text {n}"))
    d.decide(make_application(description="text 0"))  # cache
    u = tmp_db.usage("2026-11-19", "gemini-decision-1")
    assert u.requests == 4
    assert u.tokens == real["usage"]["total_tokens"]
    assert d.quota()["used_today"] == 4


@respx.mock
def test_G10_daily_and_minute_limits_block_without_calling(tmp_db, real):
    route = respx.post(GEMINI_DECISIONS_URL).mock(return_value=httpx.Response(200, json=real))
    d = decider(tmp_db, rpd=2, rpm=200)
    d.decide(make_application(description="a"))
    d.decide(make_application(description="b"))
    assert d.decide(make_application(description="c")).reason == "quota_exhausted"
    assert route.call_count == 2

    clock = Clock(datetime(2026, 11, 19, 12, tzinfo=UTC))
    d2 = decider(tmp_db, model="m2", rpd=0, rpm=2, clock=clock)
    d2.decide(make_application(description="x"))
    d2.decide(make_application(description="y"))
    assert d2.decide(make_application(description="z")).reason == "quota_exhausted"
    clock.t += timedelta(seconds=61)
    assert d2.decide(make_application(description="z")).reason == "ok"


def test_G11_quota_day_and_reset_follow_pacific_time():
    from planlabel.usage import PACIFIC

    before = datetime(2026, 11, 20, 7, 59, tzinfo=UTC)
    after = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    assert quota_day(before, PACIFIC) == "2026-11-19"
    assert quota_day(after, PACIFIC) == "2026-11-20"
    assert next_reset(before, PACIFIC) == datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    summer = datetime(2026, 7, 1, 12, tzinfo=UTC)
    assert next_reset(summer, PACIFIC) == datetime(2026, 7, 2, 7, 0, tzinfo=UTC)
