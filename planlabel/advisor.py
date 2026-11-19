"""Conselheiro do botão Dúvida (SPEC §4.3): opinião em texto, com limites de uso."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timedelta

import httpx

from planlabel.deciders.questions import CATEGORY_DEFINITIONS, SUBCATEGORY_DEFINITIONS
from planlabel.models import CATEGORY_OF, Application, Category, Subcategory
from planlabel.usage import QuotaTracker, iso

log = logging.getLogger(__name__)


def advisor_url(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _taxonomy() -> str:
    lines = []
    for category in Category:
        lines.append(f'Category "{category.value}": {CATEGORY_DEFINITIONS[category]}')
        for sub in Subcategory:
            if CATEGORY_OF[sub] == category:
                lines.append(f"- {sub.value}: {SUBCATEGORY_DEFINITIONS[sub]}")
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Você ajuda uma pessoa a rotular planning applications irlandesas para um dataset de "
    "energia. A descrição vem em inglês.\n\nTaxonomia:\n"
    + _taxonomy()
    + "\n\nExplique em português, em até 80 palavras, qual categoria e qual subcategoria "
    "você escolheria e por quê, citando o trecho da descrição que decide. Se houver dúvida "
    "entre duas subcategorias, diga quais e o que faria pender para cada uma."
)

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {"type": "STRING", "enum": [c.value for c in Category]},
        "subcategory": {"type": "STRING", "enum": [s.value for s in Subcategory]},
        "text": {"type": "STRING"},
    },
    "required": ["category", "subcategory", "text"],
    "propertyOrdering": ["category", "subcategory", "text"],
}


class AdvisorUnavailable(Exception):
    """Um limite foi atingido (ou não há chave); `status` diz qual e até quando."""

    def __init__(self, status: dict) -> None:
        super().__init__(status.get("reason"))
        self.status = status


class AdvisorError(Exception):
    """O modelo não respondeu ou respondeu algo inválido."""

    def __init__(self, message: str, status: dict | None = None) -> None:
        super().__init__(message)
        self.status = status or {}


class NoneAdvisor:
    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def status(self) -> dict:
        return {
            "model": self.model,
            "available": False,
            "reason": "disabled",
            "retry_at": None,
            "rpm_used": 0,
            "rpm_limit": 0,
            "tpm_used": 0,
            "tpm_limit": 0,
            "rpd_used": 0,
            "rpd_limit": 0,
        }

    def opinion(self, app: Application) -> dict:
        raise AdvisorUnavailable(self.status())


class GeminiAdvisor:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        client: httpx.Client,
        tracker: QuotaTracker,
        timeout_s: float = 20.0,
        cache_size: int = 128,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client
        self.tracker = tracker
        self._timeout = timeout_s
        self._blocked_until: datetime | None = None
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    @staticmethod
    def estimate_tokens(description: str = "") -> int:
        return (len(SYSTEM_PROMPT) + len(description)) // 4 + 300

    def _block(self, description: str = "") -> tuple[str, datetime] | None:
        now = self.tracker.clock()
        if self._blocked_until and now < self._blocked_until:
            return "rate_limited", self._blocked_until
        return self.tracker.blocked(extra_tokens=self.estimate_tokens(description))

    def status(self, description: str = "") -> dict:
        t = self.tracker
        blocked = self._block(description)
        minute_requests, minute_tokens = t.window()
        quota = t.quota()
        return {
            "model": self.model,
            "available": blocked is None,
            "reason": blocked[0] if blocked else None,
            "retry_at": iso(blocked[1]) if blocked else None,
            "rpm_used": minute_requests,
            "rpm_limit": t.rpm,
            "tpm_used": minute_tokens,
            "tpm_limit": t.tpm,
            "rpd_used": quota["used_today"],
            "rpd_limit": t.rpd,
        }

    def opinion(self, app: Application) -> dict:
        key = hashlib.sha256(app.description.encode()).hexdigest()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        if self._block(app.description):
            raise AdvisorUnavailable(self.status(app.description))
        entry = self.tracker.record_request()
        try:
            resp = self._client.post(
                advisor_url(self.model),
                headers={"x-goog-api-key": self._api_key},
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": [{"role": "user", "parts": [{"text": app.description}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "responseMimeType": "application/json",
                        "responseSchema": RESPONSE_SCHEMA,
                    },
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise AdvisorError(f"falha de rede: {exc}", self.status()) from exc
        if resp.status_code == 429:
            try:
                wait = float(resp.headers.get("Retry-After", "60"))
            except ValueError:
                wait = 60.0
            self._blocked_until = self.tracker.clock() + timedelta(seconds=wait)
            raise AdvisorUnavailable(self.status())
        if resp.status_code != 200:
            log.warning("%s: HTTP %s %s", self.model, resp.status_code, resp.text[:300])
            raise AdvisorError(f"HTTP {resp.status_code}", self.status())
        try:
            body = resp.json()
            self.tracker.add_tokens(
                entry, int((body.get("usageMetadata") or {}).get("totalTokenCount") or 0)
            )
            data = json.loads(body["candidates"][0]["content"]["parts"][0]["text"])
            result = {
                "model": self.model,
                "category": Category(data["category"]).value,
                "subcategory": Subcategory(data["subcategory"]).value,
                "text": str(data["text"]).strip(),
            }
            if not result["text"]:
                raise ValueError("texto vazio")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            log.warning("%s: resposta inválida: %s", self.model, exc)
            raise AdvisorError(f"resposta inválida: {exc}", self.status()) from exc
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result
