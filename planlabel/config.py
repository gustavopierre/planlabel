"""Configuração por variáveis de ambiente e `.env` (SPEC §7)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["gemini", "openrouter"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PLANLABEL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    db_path: Path = Path("data/labels.sqlite3")
    translator: str = "google,mymemory"
    ids_ttl_s: int = 86400
    host: str = "127.0.0.1"
    port: int = 8000

    # Os modelos são obrigatórios e ficam no .env (decisão do dono, 2026-11-19).
    model1_provider: Provider
    model1_id: str = Field(min_length=1)
    model1_rpm: int = 200
    model1_rpd: int = 10000
    model2_provider: Provider
    model2_id: str = Field(min_length=1)
    model2_rpm: int = 0
    model2_rpd: int = 0
    decider_timeout_s: float = 10.0

    advisor_id: str = Field(min_length=1)
    advisor_rpm: int = 15
    advisor_tpm: int = 25000
    advisor_rpd: int = 1000

    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
