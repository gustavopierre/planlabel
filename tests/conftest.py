"""Fixtures e fakes compartilhados (TDD §2)."""

from __future__ import annotations

import random
import threading
from pathlib import Path

import pytest

from planlabel.models import Application, Decision, SlotResult, Subcategory
from planlabel.repository import Repository
from planlabel.sources.arcgis import SourceError

FIXTURES = Path(__file__).parent / "fixtures"
SUBS = [s.value for s in Subcategory]


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def make_application(source="abp", n=1, **over) -> Application:
    data = {
        "source": source,
        "source_layer": "abp_3" if source == "abp" else "epl_0",
        "source_object_id": n,
        "application_number": f"{source.upper()}-{n}",
        "planning_authority": "Meath County Council",
        "description": f"Description {source} {n}",
        "application_url": f"https://example.ie/{source}/{n}",
    }
    data.update(over)
    return Application(**data)


class FakeSource:
    """Fonte em memória: `records` mapeia OBJECTID → Application (ou None = inválido)."""

    def __init__(self, name: str, records: dict[int, Application | None], fail: bool = False):
        self.name = name
        self.records = records
        self.fail = fail
        self.fetched: list[int] = []
        self._lock = threading.Lock()

    def list_ids(self) -> list[int]:
        if self.fail:
            raise SourceError(f"{self.name} fora do ar")
        return sorted(self.records)

    def fetch(self, object_id: int) -> Application | None:
        if self.fail:
            raise SourceError(f"{self.name} fora do ar")
        with self._lock:
            self.fetched.append(object_id)
        return self.records[object_id]


def fake_sources(n: int = 30) -> list[FakeSource]:
    return [
        FakeSource("abp", {i: make_application("abp", i) for i in range(1, n + 1)}),
        FakeSource("eplanning", {i: make_application("eplanning", i) for i in range(1, n + 1)}),
    ]


def decision_for(model: str, sub: str = "wind", cat: str = "energy") -> Decision:
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


class FakeDecider:
    """Decisor programável: `answer` é (sub, cat), None (falha) ou um SlotResult pronto."""

    def __init__(self, slot: int, model: str, answer=("wind", "energy"), delay: float = 0.0):
        self.slot = slot
        self.model = model
        self.answer = answer
        self.delay = delay
        self.calls = 0

    def decide(self, app: Application) -> SlotResult:
        import time

        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if isinstance(self.answer, SlotResult):
            return self.answer
        if self.answer is None:
            return SlotResult(slot=self.slot, model=self.model, reason="error")
        sub, cat = self.answer
        return SlotResult(
            slot=self.slot,
            model=self.model,
            decision=decision_for(self.model, sub, cat),
            reason="ok",
        )

    def quota(self):
        return None


def fake_deciders(answer1=("wind", "energy"), answer2=("wind", "energy")) -> dict[int, FakeDecider]:
    return {
        1: FakeDecider(1, "gemini-decision-1", answer1),
        2: FakeDecider(2, "typesafe/jev-1.14", answer2),
    }


@pytest.fixture
def rng() -> random.Random:
    return random.Random(42)


@pytest.fixture
def tmp_db(tmp_path) -> Repository:
    return Repository(tmp_path / "labels.sqlite3")
