import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from planlabel.advisor import (
    AdvisorError,
    AdvisorUnavailable,
    GeminiAdvisor,
    NoneAdvisor,
    advisor_url,
)
from planlabel.repository import Repository
from planlabel.usage import QuotaTracker
from tests.conftest import make_application

MODEL = "gemini-3.5-flash-lite"
URL = advisor_url(MODEL)


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 19, 20, 0, tzinfo=UTC)  # 12:00 no Pacífico

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def real(fixtures_dir):
    return json.loads((fixtures_dir / "gemini" / "advisor_wind_valid.json").read_text())["response"]


def reply(tokens=210, category="energy", subcategory="wind", text="Escolhi wind."):
    payload = json.dumps({"category": category, "subcategory": subcategory, "text": text})
    return {
        "candidates": [{"content": {"parts": [{"text": payload}]}}],
        "usageMetadata": {"totalTokenCount": tokens},
    }


def make(repo, clock, *, key="k", rpm=15, tpm=25000, rpd=1000):
    tracker = QuotaTracker(repo, MODEL, rpm=rpm, tpm=tpm, rpd=rpd, clock=clock)
    return GeminiAdvisor(model=MODEL, api_key=key, client=httpx.Client(), tracker=tracker)


@respx.mock
def test_H01_request_uses_same_key_and_json_output(tmp_db, real):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=real))
    make(tmp_db, Clock(), key="segredo").opinion(make_application(description="7 turbines"))
    req = route.calls.last.request
    body = json.loads(req.content)
    assert req.url.path.endswith("/models/gemini-3.5-flash-lite:generateContent")
    assert req.headers["x-goog-api-key"] == "segredo"
    assert body["contents"][0]["parts"][0]["text"] == "7 turbines"
    cfg = body["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert set(cfg["responseSchema"]["properties"]) == {"category", "subcategory", "text"}
    assert "português" in body["systemInstruction"]["parts"][0]["text"]


@respx.mock
def test_H02_valid_opinion_and_failures(tmp_db, real):
    respx.post(URL).mock(
        side_effect=[
            httpx.Response(200, json=real),
            httpx.Response(200, json=reply(subcategory="nuclear")),
            httpx.Response(500),
            httpx.ReadTimeout("lento"),
        ]
    )
    adv = make(tmp_db, Clock())
    op = adv.opinion(make_application(description="a"))
    assert (op["model"], op["category"], op["subcategory"]) == (MODEL, "energy", "wind")
    assert op["text"]
    for desc in ("b", "c", "d"):
        with pytest.raises(AdvisorError):
            adv.opinion(make_application(description=desc))


@respx.mock
def test_H03_requests_per_minute_limit(tmp_db):
    respx.post(URL).mock(return_value=httpx.Response(200, json=reply(tokens=10)))
    clock = Clock()
    adv = make(tmp_db, clock, rpm=15)
    for n in range(15):
        adv.opinion(make_application(description=f"d{n}"))
        clock.t += timedelta(seconds=1)
    status = adv.status()
    assert (status["available"], status["reason"]) == (False, "rpm")
    first = datetime(2026, 11, 19, 20, 0, tzinfo=UTC)
    assert status["retry_at"] == (first + timedelta(seconds=60)).isoformat(timespec="seconds")
    with pytest.raises(AdvisorUnavailable):
        adv.opinion(make_application(description="x"))
    clock.t = first + timedelta(seconds=60)
    assert adv.status()["available"] is True


@respx.mock
def test_H04_tokens_per_minute_limit(tmp_db):
    respx.post(URL).mock(return_value=httpx.Response(200, json=reply(tokens=24800)))
    clock = Clock()
    adv = make(tmp_db, clock, tpm=25000)
    adv.opinion(make_application(description="d"))
    status = adv.status()
    assert (status["available"], status["reason"], status["tpm_used"]) == (False, "tpm", 24800)
    clock.t += timedelta(seconds=61)
    assert adv.status()["available"] is True


@respx.mock
def test_H05_requests_per_day_limit_survives_restart(tmp_path):
    respx.post(URL).mock(return_value=httpx.Response(200, json=reply(tokens=1)))
    path = tmp_path / "db.sqlite3"
    clock = Clock()
    adv = make(Repository(path), clock, rpd=3, rpm=0, tpm=0)
    for n in range(3):
        adv.opinion(make_application(description=f"d{n}"))
    restarted = make(Repository(path), clock, rpd=3, rpm=0, tpm=0)
    status = restarted.status()
    assert (status["available"], status["reason"], status["rpd_used"]) == (False, "rpd", 3)
    assert status["retry_at"] == "2026-11-20T08:00:00+00:00"
    clock.t = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    assert restarted.status()["available"] is True


@respx.mock
def test_H06_http_429_blocks_until_retry_after(tmp_db):
    respx.post(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "30"}))
    clock = Clock()
    adv = make(tmp_db, clock)
    with pytest.raises(AdvisorUnavailable):
        adv.opinion(make_application(description="d"))
    status = adv.status()
    assert (status["available"], status["reason"]) == (False, "rate_limited")
    clock.t += timedelta(seconds=31)
    assert adv.status()["available"] is True


@respx.mock
def test_H07_cache_does_not_call_or_count(tmp_db, real):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=real))
    adv = make(tmp_db, Clock())
    adv.opinion(make_application("abp", 1, description="same"))
    adv.opinion(make_application("eplanning", 2, description="same"))
    assert route.call_count == 1
    assert adv.status()["rpd_used"] == 1


@respx.mock
def test_H08_without_key_is_disabled(tmp_db):
    route = respx.post(URL)
    adv = NoneAdvisor(MODEL)
    status = adv.status()
    assert (status["available"], status["reason"], status["model"]) == (False, "disabled", MODEL)
    with pytest.raises(AdvisorUnavailable):
        adv.opinion(make_application())
    assert route.call_count == 0
