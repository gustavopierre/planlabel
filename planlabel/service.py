"""Regras de negócio da rotulagem (SPEC §4.1)."""

from __future__ import annotations

import logging
import random
import threading
import uuid
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from planlabel.models import Application, Counts, Label, SlotResult
from planlabel.repository import DuplicateError, Repository
from planlabel.sources.arcgis import SourceError
from planlabel.sources.registry import Source, SourceRotation

log = logging.getLogger(__name__)


class UnknownToken(Exception):
    """Token sem pendente (nunca existiu, já confirmado, pulado ou descartado)."""


class NoApplicationAvailable(Exception):
    """Nenhuma fonte conseguiu servir uma aplicação nova."""


class Decider(Protocol):
    slot: int
    model: str

    def decide(self, app: Application) -> SlotResult: ...

    def quota(self): ...


@dataclass
class Pending:
    token: str
    application: Application
    slots: dict[int, SlotResult]
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class LabelingService:
    MAX_ATTEMPTS_PER_SOURCE = 10

    def __init__(
        self,
        repo: Repository,
        sources: Sequence[Source],
        deciders: Mapping[int, Decider],
        *,
        advisor=None,
        rng: random.Random | None = None,
        max_pending: int = 100,
    ) -> None:
        if set(deciders) != {1, 2}:
            raise ValueError("são obrigatórios os decisores dos slots 1 e 2")
        self.repo = repo
        self.deciders = dict(deciders)
        self.advisor = advisor
        self._rng = rng or random.Random()
        self._rotation = SourceRotation(sources)
        self._rotation_lock = threading.Lock()
        self._seen: dict[str, set[int]] = {s.name: set() for s in sources}
        self._pending: OrderedDict[str, Pending] = OrderedDict()
        self._pending_lock = threading.Lock()
        self._max_pending = max_pending

    # -- pendentes ---------------------------------------------------------------

    def empty_slots(self) -> tuple[SlotResult, SlotResult]:
        return tuple(
            SlotResult(slot=n, model=self.deciders[n].model, reason="not_requested") for n in (1, 2)
        )

    def _get(self, token: str) -> Pending:
        with self._pending_lock:
            pending = self._pending.get(token)
        if pending is None:
            raise UnknownToken(token)
        return pending

    def _pop(self, token: str) -> Pending:
        with self._pending_lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            raise UnknownToken(token)
        return pending

    # -- busca -------------------------------------------------------------------

    def _try_source(self, source: Source) -> Application | None:
        ids = source.list_ids()
        seen = self._seen[source.name]
        for _ in range(self.MAX_ATTEMPTS_PER_SOURCE):
            unseen = len(ids) - len(seen)
            if unseen <= 0:
                return None
            object_id = self._rng.choice(ids)
            while object_id in seen:
                object_id = self._rng.choice(ids)
            seen.add(object_id)
            app = source.fetch(object_id)
            if app is None:
                continue
            if self.repo.exists(app.source, app.planning_authority, app.application_number):
                continue
            return app
        return None

    def next_application(self) -> Pending:
        # O lock cobre a busca inteira: o rodízio é único no servidor e as chamadas
        # concorrentes não repetem nem pulam a vez de uma fonte.
        with self._rotation_lock:
            for source in self._rotation.order():
                try:
                    app = self._try_source(source)
                except SourceError as exc:
                    log.warning("fonte %s falhou: %s", source.name, exc)
                    continue
                if app is not None:
                    self._rotation.served(source)
                    break
            else:
                raise NoApplicationAvailable("nenhuma fonte serviu uma aplicação nova")
        pending = Pending(
            token=str(uuid.uuid4()),
            application=app,
            slots={s.slot: s for s in self.empty_slots()},
        )
        with self._pending_lock:
            self._pending[pending.token] = pending
            while len(self._pending) > self._max_pending:
                self._pending.popitem(last=False)
        return pending

    # -- rótulo ------------------------------------------------------------------

    def confirm(self, token: str, label: Label) -> Counts:
        pending = self._get(token)
        app = pending.application
        try:
            if self.repo.exists(app.source, app.planning_authority, app.application_number):
                raise DuplicateError(
                    f"{app.source} {app.planning_authority} {app.application_number}"
                )
            self.repo.save(app, label, pending.slots[1], pending.slots[2])
        except DuplicateError:
            self._discard(token)
            raise
        self._pop(token)
        return self.repo.counts()

    def _discard(self, token: str) -> None:
        with self._pending_lock:
            self._pending.pop(token, None)

    def skip(self, token: str) -> None:
        self._pop(token)

    def counts(self) -> Counts:
        return self.repo.counts()
