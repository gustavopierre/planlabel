import pytest

from planlabel.translator import (
    CachedTranslator,
    GoogleTranslator,
    NoneTranslator,
    TranslationError,
    make_translator,
)


class CountingBackend:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def translate(self, text: str) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("serviço fora")
        return f"PT:{text}"


def test_T01_none_translator_returns_original():
    assert NoneTranslator().translate("wind farm") == "wind farm"


def test_T02_cache_calls_backend_once():
    backend = CountingBackend()
    t = CachedTranslator(backend)
    assert t.translate("seven turbines") == "PT:seven turbines"
    assert t.translate("seven turbines") == "PT:seven turbines"
    assert backend.calls == 1


def test_T03_backend_failure_raises_translation_error():
    t = CachedTranslator(CountingBackend(fail=True))
    with pytest.raises(TranslationError):
        t.translate("x")


def test_T03_google_translator_wraps_library_errors(monkeypatch):
    class Boom:
        def __init__(self, **kw):
            pass

        def translate(self, text):
            raise ConnectionError("sem rede")

    monkeypatch.setattr("planlabel.translator._DeepGoogle", Boom)
    with pytest.raises(TranslationError):
        GoogleTranslator().translate("x")


def test_T04_factory_picks_implementation():
    assert isinstance(make_translator("none"), NoneTranslator)
    google = make_translator("google")
    assert isinstance(google, CachedTranslator)
    assert isinstance(google.backend, GoogleTranslator)
    with pytest.raises(ValueError, match="tradutor"):
        make_translator("babelfish")
