"""Slot 2: typesafe/jev-1.14 pela API de decisões do OpenRouter (SPEC §4.2)."""

from __future__ import annotations

import httpx

from planlabel.deciders.base import BaseDecider
from planlabel.deciders.questions import QUESTIONS

OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"


class OpenRouterDecider(BaseDecider):
    provider = "openrouter"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        if self.model.startswith("~") or self.model.endswith("-latest"):
            raise ValueError(
                f"{self.model}: use uma versão fixa do modelo, não um alias que muda sozinho"
            )

    def _request(self, description: str) -> httpx.Response:
        # Nada do dono vai em `user`, `session_id`, `trace` ou headers opcionais.
        return self._client.post(
            OPENROUTER_DECISIONS_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self.model, "state": description, "questions": QUESTIONS},
            timeout=self._timeout,
        )

    def _tokens(self, body: dict) -> int:
        usage = body.get("usage") or {}
        return int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)

    def _model_name(self, body: dict) -> str:
        return str(body.get("model") or self.model)
