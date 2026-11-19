"""Domínio: taxonomia, aplicação, rótulo humano e decisão de modelo (SPEC §1.1 e §4)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator, model_validator


class Category(StrEnum):
    ENERGY = "energy"
    NOT_ENERGY = "not_energy"


class Subcategory(StrEnum):
    """Ordem canônica do §1.1 (exibição, teclado)."""

    HYBRID = "hybrid"
    WIND = "wind"
    SOLAR = "solar"
    BESS = "bess"
    HYDRO = "hydro"
    SUBSTATION = "substation"
    ENERGY_SUPPORT = "energy_support"
    LEU = "leu"
    DATA_CENTRE = "data_centre"
    NOT_ENERGY = "not_energy"
    LOW_ENERGY = "low_energy"


CATEGORY_OF: dict[Subcategory, Category] = {
    sub: (
        Category.NOT_ENERGY
        if sub in (Subcategory.NOT_ENERGY, Subcategory.LOW_ENERGY)
        else Category.ENERGY
    )
    for sub in Subcategory
}

SOURCE_LABELS = {"abp": "ABP", "eplanning": "ePlanning"}


def normalize_text(value: str) -> str:
    """strip() + espaços internos (incluindo quebras de linha) colapsados."""
    return " ".join((value or "").split())


class Application(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Literal["abp", "eplanning"]
    source_layer: Literal["abp_3", "epl_0", "epl_1"]
    source_object_id: int
    application_number: str
    planning_authority: str = ""
    description: str
    application_url: str = ""

    @field_validator("application_number", "planning_authority", "description", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> str:
        return normalize_text(str(value)) if value is not None else ""

    @field_validator("application_number", "description")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("não pode ser vazio")
        return value

    @field_validator("application_url", mode="before")
    @classmethod
    def _url(cls, value: object) -> str:
        url = (str(value) if value is not None else "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            raise ValueError("link deve começar com http:// ou https://")
        return url

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS[self.source]

    def public(self) -> dict:
        """Campos exibidos ao usuário (SPEC §5)."""
        return {
            "source": self.source,
            "source_label": self.source_label,
            "application_number": self.application_number,
            "planning_authority": self.planning_authority,
            "description": self.description,
            "application_url": self.application_url,
        }


class Label(BaseModel):
    """Rótulo humano: categoria escolhida primeiro, subcategoria dela depois."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: Category
    subcategory: Subcategory

    @model_validator(mode="after")
    def _coherent(self) -> Label:
        if CATEGORY_OF[self.subcategory] != self.category:
            raise ValueError(
                f"subcategoria {self.subcategory} não pertence à categoria {self.category}"
            )
        return self


def to_percentages(probabilities: Mapping[str, float], keys: list[str]) -> dict[str, int]:
    """Probabilidades (soma ~1) → percentuais inteiros que somam 100 (maior resto).

    Levanta ValueError se faltar ou sobrar chave, se algum valor sair de 0..1 ou se a
    soma ficar fora de 0,98–1,02.
    """
    if set(probabilities) != set(keys):
        missing = sorted(set(keys) - set(probabilities))
        extra = sorted(set(probabilities) - set(keys))
        raise ValueError(f"opções inválidas (faltando {missing}, sobrando {extra})")
    values = {}
    for key in keys:
        value = probabilities[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"probabilidade não numérica em {key}")
        if not (0.0 <= float(value) <= 1.0) or math.isnan(float(value)):
            raise ValueError(f"probabilidade fora de 0..1 em {key}")
        values[key] = float(value)
    total = sum(values.values())
    if not (0.98 <= total <= 1.02):
        raise ValueError(f"probabilidades somam {total:.3f}, esperado ~1")
    raw = {k: v / total * 100 for k, v in values.items()}
    pct = {k: math.floor(v) for k, v in raw.items()}
    remainder = 100 - sum(pct.values())
    # maior resto; empate pela ordem canônica (estável)
    order = sorted(keys, key=lambda k: (-(raw[k] - pct[k]), keys.index(k)))
    for key in order[:remainder]:
        pct[key] += 1
    return {k: pct[k] for k in keys}


class _ApiAnswer(BaseModel):
    """Validação das probabilidades e da escolha de uma pergunta (erros viram ValidationError)."""

    keys: list[str]
    probabilities: dict[str, float]
    choice: str
    percentages: dict[str, int] = {}

    @model_validator(mode="after")
    def _check(self) -> _ApiAnswer:
        if self.choice not in self.keys:
            raise ValueError(f"escolha desconhecida: {self.choice}")
        self.percentages = to_percentages(self.probabilities, self.keys)
        return self


class Decision(BaseModel):
    """Decisão de um modelo: duas escolhas independentes, que podem se contradizer."""

    model_config = ConfigDict(frozen=True)

    model: str
    subcategory_distribution: dict[Subcategory, int]
    category_distribution: dict[Category, int]
    subcategory: Subcategory
    category: Category

    @model_validator(mode="after")
    def _distributions(self) -> Decision:
        for dist, enum in (
            (self.subcategory_distribution, Subcategory),
            (self.category_distribution, Category),
        ):
            if set(dist) != set(enum):
                raise ValueError("distribuição incompleta")
            if any(not 0 <= v <= 100 for v in dist.values()) or sum(dist.values()) != 100:
                raise ValueError("distribuição deve ter valores 0..100 somando 100")
        return self

    @computed_field
    @property
    def subcategory_pct(self) -> int:
        return self.subcategory_distribution[self.subcategory]

    @computed_field
    @property
    def category_pct(self) -> int:
        return self.category_distribution[self.category]

    @computed_field
    @property
    def consistent(self) -> bool:
        return CATEGORY_OF[self.subcategory] == self.category

    @classmethod
    def from_api(
        cls,
        *,
        model: str,
        subcategory_probabilities: Mapping[str, float],
        subcategory_choice: str,
        category_probabilities: Mapping[str, float],
        category_choice: str,
    ) -> Decision:
        sub = _ApiAnswer(
            keys=[s.value for s in Subcategory],
            probabilities=dict(subcategory_probabilities),
            choice=subcategory_choice,
        )
        cat = _ApiAnswer(
            keys=[c.value for c in Category],
            probabilities=dict(category_probabilities),
            choice=category_choice,
        )
        return cls(
            model=model,
            subcategory_distribution={Subcategory(k): v for k, v in sub.percentages.items()},
            category_distribution={Category(k): v for k, v in cat.percentages.items()},
            subcategory=Subcategory(sub.choice),
            category=Category(cat.choice),
        )

    def stored(self) -> str:
        """Conteúdo de mN_decision (SPEC §3): só as escolhas de maior percentual."""
        return json.dumps(
            {
                "category": self.category.value,
                "category_pct": self.category_pct,
                "subcategory": self.subcategory.value,
                "subcategory_pct": self.subcategory_pct,
            }
        )


Reason = Literal["ok", "error", "rate_limited", "quota_exhausted", "no_key", "not_requested"]


class SlotResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    slot: Literal[1, 2]
    model: str
    decision: Decision | None = None
    reason: Reason = "not_requested"


class Counts(BaseModel):
    total: int = 0
    energy: int = 0
    not_energy: int = 0
    by_subcategory: dict[str, int]

    @classmethod
    def empty(cls) -> Counts:
        return cls(by_subcategory={s.value: 0 for s in Subcategory})
