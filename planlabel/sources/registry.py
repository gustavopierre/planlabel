"""Rodízio de fontes (SPEC §4.1): uma fonte por vez, ordem fixa, posição única no servidor."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from planlabel.models import Application


class Source(Protocol):
    name: str

    def list_ids(self) -> list[int]: ...

    def fetch(self, object_id: int) -> Application | None: ...


class SourceRotation:
    """Guarda a posição do rodízio. Não é thread-safe: quem usa segura o lock."""

    def __init__(self, sources: Sequence[Source]) -> None:
        if not sources:
            raise ValueError("é preciso ao menos uma fonte")
        self.sources = list(sources)
        self._next = 0

    def order(self) -> list[Source]:
        """Fontes a tentar nesta chamada, começando pela da vez."""
        n = len(self.sources)
        return [self.sources[(self._next + i) % n] for i in range(n)]

    def served(self, source: Source) -> None:
        """A próxima chamada começa na fonte depois da que serviu."""
        self._next = (self.sources.index(source) + 1) % len(self.sources)
