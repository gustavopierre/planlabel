"""Persistência em SQLite (SPEC §3). SQL explícito, uma conexão por operação."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from planlabel.models import Application, Counts, Label, SlotResult, Subcategory

ENERGY_SUBS = (
    "'hybrid','wind','solar','bess','hydro','substation','energy_support','leu','data_centre'"
)
NOT_ENERGY_SUBS = "'not_energy','low_energy'"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS labeled_application (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT    NOT NULL CHECK (source IN ('abp','eplanning')),
    source_layer        TEXT    NOT NULL CHECK (source_layer IN ('abp_3','epl_0','epl_1')),
    application_number  TEXT    NOT NULL CHECK (length(trim(application_number)) > 0),
    planning_authority  TEXT    NOT NULL DEFAULT '',
    source_object_id    INTEGER NOT NULL,
    description         TEXT    NOT NULL CHECK (length(trim(description)) > 0),
    application_url     TEXT    NOT NULL DEFAULT '',
    category            TEXT    NOT NULL CHECK (category IN ('energy','not_energy')),
    subcategory         TEXT    NOT NULL,
    labeled_at          TEXT    NOT NULL,
    m1_model            TEXT    NOT NULL CHECK (length(trim(m1_model)) > 0),
    m1_decision         TEXT    CHECK (m1_decision IS NULL OR json_valid(m1_decision)),
    m2_model            TEXT    NOT NULL CHECK (length(trim(m2_model)) > 0),
    m2_decision         TEXT    CHECK (m2_decision IS NULL OR json_valid(m2_decision)),
    CHECK ((category = 'energy' AND subcategory IN ({ENERGY_SUBS}))
        OR (category = 'not_energy' AND subcategory IN ({NOT_ENERGY_SUBS}))),
    UNIQUE (source, planning_authority, application_number)
);

CREATE TABLE IF NOT EXISTS model_usage (
    day       TEXT    NOT NULL,
    model     TEXT    NOT NULL,
    requests  INTEGER NOT NULL DEFAULT 0 CHECK (requests >= 0),
    tokens    INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    PRIMARY KEY (day, model)
);
"""


class DuplicateError(Exception):
    """A aplicação já está no banco (mesma fonte, conselho e número)."""


@dataclass(frozen=True)
class Usage:
    requests: int = 0
    tokens: int = 0


class Repository:
    def __init__(
        self, path: str | Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def exists(self, source: str, authority: str, number: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM labeled_application"
                " WHERE source = ? AND planning_authority = ? AND application_number = ?",
                (source, authority, number),
            ).fetchone()
        return row is not None

    def save(self, app: Application, label: Label, slot1: SlotResult, slot2: SlotResult) -> int:
        row = (
            app.source,
            app.source_layer,
            app.application_number,
            app.planning_authority,
            app.source_object_id,
            app.description,
            app.application_url,
            label.category.value,
            label.subcategory.value,
            self._clock().astimezone(UTC).isoformat(timespec="seconds"),
            slot1.model,
            slot1.decision.stored() if slot1.decision else None,
            slot2.model,
            slot2.decision.stored() if slot2.decision else None,
        )
        try:
            with closing(self._connect()) as conn, conn:
                cur = conn.execute(
                    "INSERT INTO labeled_application (source, source_layer, application_number,"
                    " planning_authority, source_object_id, description, application_url,"
                    " category, subcategory, labeled_at, m1_model, m1_decision, m2_model,"
                    " m2_decision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
                return int(cur.lastrowid)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise DuplicateError(
                    f"{app.source} {app.planning_authority} {app.application_number}"
                ) from exc
            raise

    def counts(self) -> Counts:
        counts = Counts.empty()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT category, subcategory, COUNT(*) FROM labeled_application"
                " GROUP BY category, subcategory"
            ).fetchall()
        for category, subcategory, n in rows:
            counts.total += n
            if category == "energy":
                counts.energy += n
            else:
                counts.not_energy += n
            if subcategory in {s.value for s in Subcategory}:
                counts.by_subcategory[subcategory] += n
        return counts

    def add_usage(self, day: str, model: str, requests: int = 1, tokens: int = 0) -> Usage:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO model_usage (day, model, requests, tokens) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (day, model) DO UPDATE SET"
                " requests = requests + excluded.requests, tokens = tokens + excluded.tokens",
                (day, model, requests, tokens),
            )
            row = conn.execute(
                "SELECT requests, tokens FROM model_usage WHERE day = ? AND model = ?",
                (day, model),
            ).fetchone()
        return Usage(*row)

    def usage(self, day: str, model: str) -> Usage:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT requests, tokens FROM model_usage WHERE day = ? AND model = ?",
                (day, model),
            ).fetchone()
        return Usage(*row) if row else Usage()
