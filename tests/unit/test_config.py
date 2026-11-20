import pytest
from pydantic import ValidationError

from planlabel.config import Settings

REQUIRED = {
    "PLANLABEL_MODEL1_PROVIDER": "gemini",
    "PLANLABEL_MODEL1_ID": "gemini-decision-1",
    "PLANLABEL_MODEL2_PROVIDER": "openrouter",
    "PLANLABEL_MODEL2_ID": "typesafe/jev-1.14",
    "PLANLABEL_ADVISOR_ID": "gemini-3.5-flash-lite",
}


@pytest.fixture
def env(monkeypatch):
    for key in [*list(REQUIRED), "GEMINI_API_KEY", "OPENROUTER_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_O07_all_required_present_gives_defaults(env):
    s = Settings(_env_file=None)
    assert (s.model1_provider, s.model1_id) == ("gemini", "gemini-decision-1")
    assert (s.model1_rpm, s.model1_rpd) == (200, 10000)
    assert (s.model2_rpm, s.model2_rpd) == (0, 0)
    assert (s.advisor_rpm, s.advisor_tpm, s.advisor_rpd) == (15, 25000, 1000)
    assert s.translator == "google,mymemory"
    assert (s.host, s.port) == ("127.0.0.1", 8000)
    assert s.gemini_api_key is None


@pytest.mark.parametrize("missing", list(REQUIRED))
def test_O07_missing_model_setting_stops_startup_naming_it(env, missing):
    env.delenv(missing)
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None)
    assert missing.removeprefix("PLANLABEL_").lower() in str(err.value).lower()


def test_O07_unknown_provider_rejected(env):
    env.setenv("PLANLABEL_MODEL2_PROVIDER", "acme")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_O07_keys_read_without_prefix(env):
    env.setenv("GEMINI_API_KEY", "g")
    env.setenv("OPENROUTER_API_KEY", "o")
    s = Settings(_env_file=None)
    assert (s.gemini_api_key, s.openrouter_api_key) == ("g", "o")
