import random
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from planlabel.api import create_app
from planlabel.models import SlotResult
from planlabel.repository import Repository
from planlabel.translator import TranslationError
from planlabel.usage import QuotaTracker
from tests.conftest import FakeAdvisor, FakeDecider, FakeSource, fake_sources, make_application

SUBS = [
    "hybrid",
    "wind",
    "solar",
    "bess",
    "hydro",
    "substation",
    "energy_support",
    "leu",
    "data_centre",
    "not_energy",
    "low_energy",
]


class EchoTranslator:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def translate(self, text: str) -> str:
        if self.fail:
            raise TranslationError("fora")
        return f"PT: {text}"


def build(
    tmp_path,
    *,
    sources=None,
    answer1=("wind", "energy"),
    answer2=("wind", "energy"),
    advisor=None,
    translator=None,
):
    repo = Repository(tmp_path / "labels.sqlite3")
    deciders = {
        1: FakeDecider(
            1,
            "gemini-decision-1",
            answer1,
            tracker=QuotaTracker(repo, "gemini-decision-1", rpm=200, rpd=10000),
        ),
        2: FakeDecider(
            2, "typesafe/jev-1.14", answer2, tracker=QuotaTracker(repo, "typesafe/jev-1.14")
        ),
    }
    app = create_app(
        repo=repo,
        sources=sources if sources is not None else fake_sources(),
        deciders=deciders,
        advisor=advisor or FakeAdvisor(),
        translator=translator or EchoTranslator(),
        rng=random.Random(42),
    )
    return TestClient(app), repo, deciders


@pytest.fixture
def api(tmp_path):
    return build(tmp_path)


def label_count(repo) -> int:
    with sqlite3.connect(repo.path) as conn:
        return conn.execute("SELECT COUNT(*) FROM labeled_application").fetchone()[0]


def test_I01_index_html(api):
    client, _, _ = api
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="app"' in r.text


def test_I02_stats_shape(api):
    client, _, _ = api
    body = client.get("/api/stats").json()
    assert body["total"] == body["energy"] == body["not_energy"] == 0
    assert list(body["by_subcategory"]) == SUBS


def test_I03_next_shape(api):
    client, _, _ = api
    body = client.get("/api/next").json()
    assert set(body) == {"token", "application", "stats", "models", "advisor"}
    assert set(body["application"]) == {
        "source",
        "source_label",
        "application_number",
        "planning_authority",
        "description",
        "application_url",
    }
    assert body["application"]["source_label"] == "ABP"
    assert [m["slot"] for m in body["models"]] == [1, 2]
    assert body["models"][0]["model"] == "gemini-decision-1"
    assert body["advisor"]["available"] is True


def test_I04_label_low_energy(api):
    client, _, _ = api
    token = client.get("/api/next").json()["token"]
    r = client.post(
        "/api/labels",
        json={"token": token, "category": "not_energy", "subcategory": "low_energy"},
    )
    assert r.status_code == 201
    stats = r.json()["stats"]
    assert (stats["total"], stats["not_energy"], stats["by_subcategory"]["low_energy"]) == (1, 1, 1)


def test_I05_label_data_centre(api):
    client, _, _ = api
    token = client.get("/api/next").json()["token"]
    r = client.post(
        "/api/labels", json={"token": token, "category": "energy", "subcategory": "data_centre"}
    )
    assert r.status_code == 201
    stats = r.json()["stats"]
    assert (stats["energy"], stats["by_subcategory"]["data_centre"]) == (1, 1)


@pytest.mark.parametrize(
    "payload",
    [{"category": "energy"}, {"subcategory": "wind"}, {}],
)
def test_I06_missing_fields_422(api, payload):
    client, repo, _ = api
    token = client.get("/api/next").json()["token"]
    assert client.post("/api/labels", json={"token": token, **payload}).status_code == 422
    assert label_count(repo) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "energy", "subcategory": "nuclear"},
        {"category": "energy", "subcategory": "low_energy"},
        {"category": "not_energy", "subcategory": "wind"},
    ],
)
def test_I07_invalid_or_incoherent_422(api, payload):
    client, repo, _ = api
    token = client.get("/api/next").json()["token"]
    assert client.post("/api/labels", json={"token": token, **payload}).status_code == 422
    assert label_count(repo) == 0


def test_I08_unknown_token_404(api):
    client, _, _ = api
    r = client.post(
        "/api/labels", json={"token": "nope", "category": "energy", "subcategory": "wind"}
    )
    assert r.status_code == 404


def test_I09_same_token_twice(api):
    client, repo, _ = api
    token = client.get("/api/next").json()["token"]
    payload = {"token": token, "category": "energy", "subcategory": "wind"}
    assert client.post("/api/labels", json=payload).status_code == 201
    assert client.post("/api/labels", json=payload).status_code == 404
    assert label_count(repo) == 1


def test_I09_duplicate_saved_elsewhere_409(api):
    client, repo, _deciders = api
    body = client.get("/api/next").json()
    a = body["application"]
    from planlabel.models import Application, Label

    app = Application(
        source=a["source"],
        source_layer="abp_3",
        source_object_id=999,
        application_number=a["application_number"],
        planning_authority=a["planning_authority"],
        description="x",
    )
    repo.save(
        app,
        Label(category="energy", subcategory="wind"),
        SlotResult(slot=1, model="a"),
        SlotResult(slot=2, model="b"),
    )
    r = client.post(
        "/api/labels", json={"token": body["token"], "category": "energy", "subcategory": "wind"}
    )
    assert r.status_code == 409


def test_I10_skip(api):
    client, repo, _ = api
    token = client.get("/api/next").json()["token"]
    assert client.post("/api/skip", json={"token": token}).status_code == 204
    r = client.post(
        "/api/labels", json={"token": token, "category": "energy", "subcategory": "wind"}
    )
    assert r.status_code == 404
    assert client.post("/api/skip", json={"token": token}).status_code == 404
    assert label_count(repo) == 0


def test_I11_all_sources_down_503(tmp_path):
    srcs = fake_sources()
    for s in srcs:
        s.fail = True
    client, _, _ = build(tmp_path, sources=srcs)
    r = client.get("/api/next")
    assert r.status_code == 503
    assert r.json()["detail"]


def test_I12_translate(tmp_path):
    client, _, _ = build(tmp_path)
    assert client.post("/api/translate", json={"text": "wind"}).json() == {
        "translation": "PT: wind"
    }
    assert client.post("/api/translate", json={"text": "x" * 4001}).status_code == 422
    failing, _, _ = build(tmp_path / "b", translator=EchoTranslator(fail=True))
    assert failing.post("/api/translate", json={"text": "wind"}).status_code == 502


def test_I13_saved_record_matches_displayed(api):
    client, repo, _ = api
    body = client.get("/api/next").json()
    client.post(
        "/api/labels", json={"token": body["token"], "category": "energy", "subcategory": "solar"}
    )
    with sqlite3.connect(repo.path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM labeled_application").fetchone()
    a = body["application"]
    for field in (
        "source",
        "application_number",
        "planning_authority",
        "description",
        "application_url",
    ):
        assert row[field] == a[field]
    assert (row["category"], row["subcategory"]) == ("energy", "solar")


def test_I14_saved_application_never_returned_again(tmp_path):
    src = FakeSource("abp", {i: make_application("abp", i) for i in range(1, 4)})
    client, _, _ = build(tmp_path, sources=[src])
    body = client.get("/api/next").json()
    client.post(
        "/api/labels", json={"token": body["token"], "category": "energy", "subcategory": "wind"}
    )
    number = body["application"]["application_number"]
    for _ in range(50):
        r = client.get("/api/next")
        if r.status_code == 503:
            break
        assert r.json()["application"]["application_number"] != number
        client.post("/api/skip", json={"token": r.json()["token"]})


def test_I15_decide_both_slots_never_writes(api):
    client, repo, _ = api
    token = client.get("/api/next").json()["token"]
    with patch.object(Repository, "save", side_effect=AssertionError("escreveu")):
        for slot in (1, 2):
            body = client.post("/api/decide", json={"token": token, "slot": slot}).json()
            d = body["decision"]
            assert body["slot"] == slot
            assert body["reason"] == "ok"
            assert list(d["subcategory_distribution"]) == SUBS
            assert set(d["category_distribution"]) == {"energy", "not_energy"}
            assert (d["subcategory"], d["category"], d["consistent"]) == ("wind", "energy", True)
            assert d["subcategory_pct"] == 100
    assert label_count(repo) == 0


def test_I16_failing_decider_returns_null(tmp_path):
    client, repo, _ = build(tmp_path, answer1=None)
    token = client.get("/api/next").json()["token"]
    body = client.post("/api/decide", json={"token": token, "slot": 1}).json()
    assert (body["decision"], body["reason"]) == (None, "error")
    assert label_count(repo) == 0


def test_I17_decide_then_skip_writes_nothing(api):
    client, repo, _ = api
    token = client.get("/api/next").json()["token"]
    client.post("/api/decide", json={"token": token, "slot": 1})
    client.post("/api/decide", json={"token": token, "slot": 2})
    client.post("/api/skip", json={"token": token})
    assert label_count(repo) == 0


def test_I18_decide_and_doubt_errors(api):
    client, _, _ = api
    assert client.post("/api/decide", json={"token": "nope", "slot": 1}).status_code == 404
    assert client.post("/api/doubt", json={"token": "nope"}).status_code == 404
    token = client.get("/api/next").json()["token"]
    assert client.post("/api/decide", json={"token": token, "slot": 3}).status_code == 422


@pytest.mark.parametrize(
    "extra",
    [
        {"m1_decision": '{"subcategory":"wind"}'},
        {"m2_model": "forjado"},
        {"labeled_at": "2020-01-01"},
    ],
)
def test_I19_client_cannot_forge_fields(api, extra):
    client, repo, _ = api
    token = client.get("/api/next").json()["token"]
    payload = {"token": token, "category": "energy", "subcategory": "wind", **extra}
    assert client.post("/api/labels", json=payload).status_code == 422
    assert label_count(repo) == 0


def test_I20_healthz_touches_nothing(tmp_path):
    srcs = fake_sources()
    for s in srcs:
        s.fail = True
    client, _, deciders = build(tmp_path, sources=srcs)
    with patch.object(Repository, "counts", side_effect=AssertionError("banco")):
        r = client.get("/healthz")
    assert r.json() == {"status": "ok"}
    assert deciders[1].calls == deciders[2].calls == 0


def test_I21_quota_fields_and_no_key_slot(tmp_path):
    no_key = SlotResult(slot=2, model="typesafe/jev-1.14", reason="no_key")
    client, _, _ = build(tmp_path, answer2=no_key)
    body = client.get("/api/next").json()
    q = body["models"][0]["quota"]
    assert set(q) == {
        "model",
        "used_today",
        "limit_day",
        "used_minute",
        "limit_minute",
        "resets_at",
    }
    assert (q["used_today"], q["limit_day"], q["limit_minute"]) == (0, 10000, 200)
    r1 = client.post("/api/decide", json={"token": body["token"], "slot": 1}).json()
    assert r1["quota"]["used_today"] == 1
    r2 = client.post("/api/decide", json={"token": body["token"], "slot": 2}).json()
    assert (r2["model"], r2["decision"], r2["reason"]) == ("typesafe/jev-1.14", None, "no_key")


def test_I22_doubt_ok_blocked_error_and_status(tmp_path):
    client, repo, _ = build(tmp_path)
    token = client.get("/api/next").json()["token"]
    r = client.post("/api/doubt", json={"token": token})
    assert r.status_code == 200
    assert r.json()["opinion"]["subcategory"] == "wind"
    assert r.json()["advisor"]["rpd_used"] == 1
    assert label_count(repo) == 0

    blocked, _, _ = build(tmp_path / "b", advisor=FakeAdvisor("blocked"))
    token = blocked.get("/api/next").json()["token"]
    r = blocked.post("/api/doubt", json={"token": token})
    assert r.status_code == 429
    assert r.json()["advisor"]["reason"] == "rpm"
    assert r.json()["advisor"]["retry_at"]
    assert blocked.get("/api/advisor").json()["available"] is False

    failing, _, _ = build(tmp_path / "c", advisor=FakeAdvisor("error"))
    token = failing.get("/api/next").json()["token"]
    assert failing.post("/api/doubt", json={"token": token}).status_code == 502


def test_build_app_wires_real_components_from_settings(tmp_path, monkeypatch):
    from planlabel.advisor import GeminiAdvisor, NoneAdvisor
    from planlabel.api import build_app
    from planlabel.config import Settings
    from planlabel.deciders.gemini import GeminiDecider
    from planlabel.deciders.openrouter import OpenRouterDecider
    from planlabel.sources.arcgis import ArcGISSource, LayeredSource

    base = {
        "model1_provider": "gemini",
        "model1_id": "gemini-decision-1",
        "model2_provider": "openrouter",
        "model2_id": "typesafe/jev-1.14",
        "advisor_id": "gemini-3.5-flash-lite",
        "db_path": tmp_path / "x.sqlite3",
        "translator": "none",
    }
    app = build_app(Settings(_env_file=None, **base, GEMINI_API_KEY="g"))
    svc = app.state.service
    assert isinstance(svc.deciders[1], GeminiDecider)
    assert isinstance(svc.deciders[2], OpenRouterDecider)
    assert (svc.deciders[1].tracker.rpm, svc.deciders[1].tracker.rpd) == (200, 10000)
    assert isinstance(svc.advisor, GeminiAdvisor)
    assert [s.name for s in svc._rotation.sources] == ["abp", "eplanning"]
    abp, epl = svc._rotation.sources
    assert isinstance(abp, ArcGISSource)
    assert isinstance(epl, LayeredSource)
    assert [layer.config.source_layer for layer in epl.layers] == ["epl_0", "epl_1"]

    swapped = build_app(
        Settings(
            _env_file=None,
            **{**base, "model1_provider": "openrouter", "model1_id": "typesafe/jev-1.13"},
        )
    )
    assert isinstance(swapped.state.service.deciders[1], OpenRouterDecider)
    assert isinstance(swapped.state.service.advisor, NoneAdvisor)
