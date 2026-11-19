"""Cotas por modelo (SPEC §4.4): dia no fuso do provedor (SQLite) e janela de 60 s (memória)."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from planlabel.repository import Repository

PACIFIC = ZoneInfo("America/Los_Angeles")
UTC_ZONE = ZoneInfo("UTC")
WINDOW = timedelta(seconds=60)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def quota_day(now: datetime, tz: ZoneInfo) -> str:
    return now.astimezone(tz).date().isoformat()


def next_reset(now: datetime, tz: ZoneInfo) -> datetime:
    """Próxima meia-noite no fuso `tz`, em UTC (respeita horário de verão)."""
    local = now.astimezone(tz)
    midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return midnight.astimezone(UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="seconds") if dt else None


class QuotaTracker:
    """Conta requisições e tokens de um modelo e diz se um limite foi atingido.

    Limite 0 = sem limite (só conta).
    """

    def __init__(
        self,
        repo: Repository,
        model: str,
        *,
        tz: ZoneInfo = PACIFIC,
        rpm: int = 0,
        rpd: int = 0,
        tpm: int = 0,
        clock: Clock = utc_now,
    ) -> None:
        self.repo = repo
        self.model = model
        self.tz = tz
        self.rpm, self.rpd, self.tpm = rpm, rpd, tpm
        self.clock = clock
        self._window: deque[list] = deque()  # [instante, tokens]
        self._lock = threading.Lock()

    def _prune(self, now: datetime) -> None:
        while self._window and now - self._window[0][0] >= WINDOW:
            self._window.popleft()

    def _today(self, now: datetime) -> int:
        return self.repo.usage(quota_day(now, self.tz), self.model).requests

    def blocked(self, extra_tokens: int = 0) -> tuple[str, datetime] | None:
        """(motivo, liberado_em) se um limite impede uma nova requisição; senão None."""
        now = self.clock()
        with self._lock:
            self._prune(now)
            if self.rpm and len(self._window) >= self.rpm:
                return "rpm", self._window[len(self._window) - self.rpm][0] + WINDOW
            if self.tpm:
                used = sum(t for _, t in self._window)
                if used + extra_tokens > self.tpm:
                    # libera quando sair da janela o suficiente para caber a estimativa
                    need = used + extra_tokens - self.tpm
                    freed = 0
                    for at, tokens in self._window:
                        freed += tokens
                        if freed >= need:
                            return "tpm", at + WINDOW
                    return "tpm", now + WINDOW
        if self.rpd and self._today(now) >= self.rpd:
            return "rpd", next_reset(now, self.tz)
        return None

    def record_request(self) -> list:
        """Soma 1 requisição (antes do envio). Devolve a entrada da janela para somar tokens."""
        now = self.clock()
        self.repo.add_usage(quota_day(now, self.tz), self.model)
        entry = [now, 0]
        with self._lock:
            self._window.append(entry)
        return entry

    def add_tokens(self, entry: list, tokens: int) -> None:
        if tokens <= 0:
            return
        self.repo.add_usage(quota_day(entry[0], self.tz), self.model, requests=0, tokens=tokens)
        with self._lock:
            entry[1] += tokens

    def window(self) -> tuple[int, int]:
        """(requisições, tokens) nos últimos 60 s."""
        now = self.clock()
        with self._lock:
            self._prune(now)
            return len(self._window), sum(t for _, t in self._window)

    def quota(self) -> dict:
        now = self.clock()
        minute, _ = self.window()
        return {
            "model": self.model,
            "used_today": self._today(now),
            "limit_day": self.rpd,
            "used_minute": minute,
            "limit_minute": self.rpm,
            "resets_at": iso(next_reset(now, self.tz)),
        }
