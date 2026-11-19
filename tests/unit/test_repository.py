import json
import sqlite3
from datetime import UTC, datetime

import pytest

from planlabel.models import Application, Decision, Label, SlotResult, Subcategory
from planlabel.repository import DuplicateError, Repository

SUBS = [s.value for s in Subcategory]


def app(**over) -> Application:
    data = {
        "source": "eplanning",
        "source_layer": "epl_0",
        "source_object_id": 7,
        "application_number": "22806",
        "planning_authority": "Meath County Council",
        "description": "7 no. wind turbines",
        "application_url": "http://www.eplanning.ie/MeathCC/AppFileRefDetails/22806/0",
    }
    data.update(over)
    return Application(**data)


def decision(model="gemini-decision-1", sub="wind", cat="energy") -> Decision:
    probs = dict.fromkeys(SUBS, 0.0)
    probs[sub] = 1.0
    cat_probs = {"energy": 0.0, "not_energy": 0.0}
    cat_probs[cat] = 1.0
    return Decision.from_api(
        model=model,
        subcategory_probabilities=probs,
        subcategory_choice=sub,
        category_probabilities=cat_probs,
        category_choice=cat,
    )


def slots(d1=None, d2=None):
    return (
        SlotResult(slot=1, model="gemini-decision-1", decision=d1, reason="ok" if d1 else "error"),
        SlotResult(
            slot=2,
            model="typesafe/jev-1.14-20261014",
            decision=d2,
            reason="ok" if d2 else "error",
        ),
    )


WIND = Label(category="energy", subcategory="wind")


@pytest.fixture
def repo(tmp_path) -> Repository:
    return Repository(tmp_path / "sub" / "labels.sqlite3")


def raw_insert(repo: Repository, **over):
    row = {
        "source": "abp",
        "source_layer": "abp_3",
        "application_number": "1",
        "planning_authority": "X",
        "source_object_id": 1,
        "description": "d",
        "application_url": "",
        "category": "energy",
        "subcategory": "wind",
        "labeled_at": "2026-11-19T00:00:00+00:00",
        "m1_model": "a",
        "m1_decision": None,
        "m2_model": "b",
        "m2_decision": None,
    }
    row.update(over)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with sqlite3.connect(repo.path) as conn:
        conn.execute(
            f"INSERT INTO labeled_application ({cols}) VALUES ({marks})", list(row.values())
        )


def test_R01_schema_created_and_reopen_is_idempotent(tmp_path):
    path = tmp_path / "labels.sqlite3"
    Repository(path)
    repo = Repository(path)
    assert repo.counts().total == 0
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert {"labeled_application", "model_usage"} <= tables
    assert mode == "wal"


def test_R02_exists_by_source_authority_number(repo):
    repo.save(app(), WIND, *slots())
    assert repo.exists("eplanning", "Meath County Council", "22806")
    assert not repo.exists("eplanning", "Offaly County Council", "22806")
    assert not repo.exists("abp", "Meath County Council", "22806")


def test_R02_same_source_other_layer_is_duplicate(repo):
    repo.save(app(), WIND, *slots())
    other_layer = app(source_layer="epl_1", source_object_id=99)
    assert repo.exists(other_layer.source, other_layer.planning_authority, "22806")
    with pytest.raises(DuplicateError):
        repo.save(other_layer, WIND, *slots())


def test_R03_duplicate_save_raises_and_total_stays_one(repo):
    repo.save(app(), WIND, *slots())
    with pytest.raises(DuplicateError):
        repo.save(app(), WIND, *slots())
    assert repo.counts().total == 1


def test_R04_db_rejects_energy_with_not_energy_subcategory(repo):
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(repo, category="energy", subcategory="low_energy")


@pytest.mark.parametrize(
    "over",
    [
        {"category": "not_energy", "subcategory": "wind"},
        {"category": "energy", "subcategory": "nuclear"},
        {"category": "maybe", "subcategory": "wind"},
    ],
)
def test_R05_db_rejects_incoherent_or_unknown_values(repo, over):
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(repo, **over)


def test_R06_counts_empty_has_all_subcategories(repo):
    c = repo.counts()
    assert (c.total, c.energy, c.not_energy) == (0, 0, 0)
    assert c.by_subcategory == dict.fromkeys(SUBS, 0)


def test_R07_counts_mixed(repo):
    repo.save(app(application_number="1"), WIND, *slots())
    repo.save(app(application_number="2"), Label(category="energy", subcategory="bess"), *slots())
    repo.save(
        app(application_number="3"),
        Label(category="not_energy", subcategory="low_energy"),
        *slots(),
    )
    c = repo.counts()
    assert (c.total, c.energy, c.not_energy) == (3, 2, 1)
    assert c.by_subcategory["wind"] == 1
    assert c.by_subcategory["bess"] == 1
    assert c.by_subcategory["low_energy"] == 1
    assert c.by_subcategory["hydro"] == 0


def test_R08_labeled_at_is_iso_utc(tmp_path):
    fixed = datetime(2026, 11, 19, 21, 30, tzinfo=UTC)
    repo = Repository(tmp_path / "l.sqlite3", clock=lambda: fixed)
    repo.save(app(), WIND, *slots())
    with sqlite3.connect(repo.path) as conn:
        (value,) = conn.execute("SELECT labeled_at FROM labeled_application").fetchone()
    assert value == "2026-11-19T21:30:00+00:00"
    assert datetime.fromisoformat(value).utcoffset().total_seconds() == 0


def test_R09_save_stores_model_names_decisions_and_url(repo):
    contradictory = decision(model="typesafe/jev-1.14-20261014", sub="wind", cat="not_energy")
    repo.save(app(), WIND, *slots(decision(), contradictory))
    repo.save(app(application_number="2"), WIND, *slots(None, None))
    with sqlite3.connect(repo.path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM labeled_application ORDER BY id").fetchall()
        sub1 = conn.execute(
            "SELECT json_extract(m1_decision, '$.subcategory') FROM labeled_application WHERE id=1"
        ).fetchone()[0]
    first, second = rows
    assert first["m1_model"] == "gemini-decision-1"
    assert first["m2_model"] == "typesafe/jev-1.14-20261014"
    assert json.loads(first["m1_decision"]) == {
        "category": "energy",
        "category_pct": 100,
        "subcategory": "wind",
        "subcategory_pct": 100,
    }
    assert json.loads(first["m2_decision"])["category"] == "not_energy"
    assert sub1 == "wind"
    assert first["application_url"].startswith("http://www.eplanning.ie/")
    assert first["source_layer"] == "epl_0"
    assert second["m1_model"] == "gemini-decision-1"
    assert second["m1_decision"] is None
    assert second["m2_decision"] is None


@pytest.mark.parametrize(
    "over",
    [
        {"m1_model": None},
        {"m2_model": "   "},
        {"m1_decision": "não é json"},
    ],
)
def test_R10_db_rejects_missing_model_or_invalid_decision(repo, over):
    with pytest.raises(sqlite3.IntegrityError):
        raw_insert(repo, **over)


def test_R10_db_accepts_null_and_contradictory_decisions(repo):
    raw_insert(repo, m1_decision=None, m2_decision='{"category":"not_energy","subcategory":"wind"}')
    assert repo.counts().total == 1


def test_R11_usage_counts_requests_and_tokens(tmp_path):
    path = tmp_path / "u.sqlite3"
    repo = Repository(path)
    for tokens in (100, 200, 0):
        repo.add_usage("2026-11-19", "gemini-decision-1", tokens=tokens)
    repo.add_usage("2026-11-19", "gemini-decision-1", requests=0, tokens=50)
    u = repo.usage("2026-11-19", "gemini-decision-1")
    assert (u.requests, u.tokens) == (3, 350)
    assert repo.usage("2026-11-20", "gemini-decision-1").requests == 0
    assert repo.usage("2026-11-19", "typesafe/jev-1.14").requests == 0
    assert Repository(path).usage("2026-11-19", "gemini-decision-1").requests == 3
