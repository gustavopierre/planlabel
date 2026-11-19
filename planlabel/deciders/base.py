"""Base comum dos modelos de decisão (SPEC §4.2): cache, cota, erros e leitura da resposta."""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict

import httpx

from planlabel.models import Application, Decision, SlotResult
from planlabel.usage import QuotaTracker

log = logging.getLogger(__name__)


def parse_answers(answers: dict, model: str) -> Decision:
    """`answers` da API de decisões → Decision. Levanta ValueError se faltar algo."""
    if not isinstance(answers, dict):
        raise ValueError("resposta sem 'answers'")
    parts = {}
    for question in ("subcategory", "category"):
        answer = answers.get(question)
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise ValueError(f"pergunta {question} sem resposta de escolha: {answer!r}")
        parts[question] = answer
    return Decision.from_api(
        model=model,
        subcategory_probabilities=parts["subcategory"].get("probabilities") or {},
        subcategory_choice=str(parts["subcategory"].get("choice")),
        category_probabilities=parts["category"].get("probabilities") or {},
        category_choice=str(parts["category"].get("choice")),
    )


class BaseDecider:
    provider = "base"

    def __init__(
        self,
        *,
        slot: int,
        model: str,
        api_key: str | None,
        client: httpx.Client,
        tracker: QuotaTracker,
        timeout_s: float = 10.0,
        cache_size: int = 256,
    ) -> None:
        self.slot = slot
        self.model = model
        self._api_key = api_key or None
        self._client = client
        self.tracker = tracker
        self._timeout = timeout_s
        self._cache: OrderedDict[str, SlotResult] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    # Cada provedor implementa:
    def _request(self, description: str) -> httpx.Response:  # pragma: no cover
        raise NotImplementedError

    def _tokens(self, body: dict) -> int:  # pragma: no cover
        raise NotImplementedError

    def _model_name(self, body: dict) -> str:
        return self.model

    def _result(self, reason: str, decision: Decision | None = None, model: str | None = None):
        return SlotResult(
            slot=self.slot, model=model or self.model, decision=decision, reason=reason
        )

    def decide(self, app: Application) -> SlotResult:
        if not self._api_key:
            return self._result("no_key")
        key = hashlib.sha256(app.description.encode()).hexdigest()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        if self.tracker.blocked():
            return self._result("quota_exhausted")
        entry = self.tracker.record_request()
        try:
            resp = self._request(app.description)
        except httpx.HTTPError as exc:
            log.warning("%s: falha de rede: %s", self.model, exc)
            return self._result("error")
        if resp.status_code == 429:
            log.warning("%s: HTTP 429", self.model)
            return self._result("rate_limited")
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code != 200 or "error" in body:
            log.warning("%s: HTTP %s %s", self.model, resp.status_code, str(body)[:300])
            return self._result("error")
        self.tracker.add_tokens(entry, self._tokens(body))
        name = self._model_name(body)
        try:
            decision = parse_answers(body.get("answers"), name)
        except ValueError as exc:
            log.warning("%s: resposta inválida: %s", self.model, exc)
            return self._result("error", model=name)
        result = self._result("ok", decision, model=name)
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result

    def quota(self) -> dict:
        return self.tracker.quota()
