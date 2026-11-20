"""Tradução da descrição para português, só para leitura (ARCHITECTURE §2.6)."""

from __future__ import annotations

import logging
from collections import OrderedDict
from threading import Lock
from typing import Protocol

from deep_translator import GoogleTranslator as _DeepGoogle
from deep_translator import MyMemoryTranslator as _DeepMyMemory

log = logging.getLogger(__name__)


class TranslationError(Exception):
    """O serviço de tradução falhou."""


class Translator(Protocol):
    def translate(self, text: str) -> str: ...


class NoneTranslator:
    def translate(self, text: str) -> str:
        return text


class GoogleTranslator:
    """Google Translate não oficial via deep-translator (sem chave)."""

    def translate(self, text: str) -> str:
        try:
            result = _DeepGoogle(source="en", target="pt").translate(text)
        except Exception as exc:  # a biblioteca levanta vários tipos
            raise TranslationError(str(exc)) from exc
        if not result:
            raise TranslationError("tradução vazia")
        return result


class MyMemoryTranslator:
    """MyMemory via deep-translator (sem chave; limite diário anônimo de caracteres)."""

    def translate(self, text: str) -> str:
        try:
            result = _DeepMyMemory(source="en-GB", target="pt-BR").translate(text)
        except Exception as exc:
            raise TranslationError(str(exc)) from exc
        if not result:
            raise TranslationError("tradução vazia")
        return result


class FallbackTranslator:
    """Tenta cada tradutor na ordem; falha só se todos falharem."""

    def __init__(self, translators: list[Translator]) -> None:
        self.translators = translators

    def translate(self, text: str) -> str:
        errors = []
        for translator in self.translators:
            try:
                return translator.translate(text)
            except TranslationError as exc:
                log.warning("%s falhou: %s", type(translator).__name__, exc)
                errors.append(str(exc))
        raise TranslationError("; ".join(errors))


class CachedTranslator:
    """Cache LRU em memória na frente de um tradutor."""

    def __init__(self, backend: Translator, size: int = 256) -> None:
        self.backend = backend
        self._size = size
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = Lock()

    def translate(self, text: str) -> str:
        with self._lock:
            if text in self._cache:
                self._cache.move_to_end(text)
                return self._cache[text]
        try:
            result = self.backend.translate(text)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(str(exc)) from exc
        with self._lock:
            self._cache[text] = result
            while len(self._cache) > self._size:
                self._cache.popitem(last=False)
        return result


BACKENDS = {"google": GoogleTranslator, "mymemory": MyMemoryTranslator}


def make_translator(name: str) -> Translator:
    """`name`: "none" ou lista separada por vírgula, tentada em ordem (ex.: "google,mymemory")."""
    if name.strip() == "none":
        return NoneTranslator()
    names = [n.strip() for n in name.split(",") if n.strip()]
    unknown = [n for n in names if n not in BACKENDS]
    if not names or unknown:
        raise ValueError(f"tradutor desconhecido: {name!r} (use google, mymemory ou none)")
    backends = [BACKENDS[n]() for n in names]
    return CachedTranslator(backends[0] if len(backends) == 1 else FallbackTranslator(backends))
