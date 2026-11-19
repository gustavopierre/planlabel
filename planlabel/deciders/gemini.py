"""Slot 1: gemini-decision-1 pela API de decisões do Gemini (SPEC §4.2)."""

from __future__ import annotations

import httpx

from planlabel.deciders.base import BaseDecider
from planlabel.deciders.questions import QUESTIONS

GEMINI_DECISIONS_URL = "https://generativelanguage.googleapis.com/v1beta/decisions"


class GeminiDecider(BaseDecider):
    provider = "gemini"

    def _request(self, description: str) -> httpx.Response:
        return self._client.post(
            GEMINI_DECISIONS_URL,
            headers={"x-goog-api-key": self._api_key},
            json={"model": self.model, "input": description, "questions": QUESTIONS},
            timeout=self._timeout,
        )

    def _tokens(self, body: dict) -> int:
        usage = body.get("usage") or {}
        return int(usage.get("total_tokens") or usage.get("total_input_tokens") or 0)
