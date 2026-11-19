"""Fixtures compartilhadas. Fixtures específicas entram junto com as tarefas que as usam."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
