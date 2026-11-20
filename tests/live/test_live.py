"""Testes contra a rede real (fontes ArcGIS e modelos). Rodar com: pytest -m live

Precisam de rede; L-03..L-05 precisam das chaves no ambiente ou no .env.
Cada execução gasta poucas requisições (3 por modelo decisor, 1 do conselheiro).
"""

from __future__ import annotations

import httpx
import pytest

from planlabel.advisor import GeminiAdvisor
from planlabel.config import Settings
from planlabel.deciders.gemini import GeminiDecider
from planlabel.deciders.openrouter import OpenRouterDecider
from planlabel.models import Application
from planlabel.sources.arcgis import FIELD_MAP, ArcGISSource
from planlabel.usage import PACIFIC, UTC_ZONE, QuotaTracker

pytestmark = pytest.mark.live

KNOWN = {
    "wind": (
        "Permission for a 10 year planning permission for a wind farm development comprising "
        "7 no. wind turbines with a maximum tip height of 150m and all associated site works.",
        "energy",
    ),
    "house": (
        "Permission for a single storey extension to the rear of existing dwelling house and "
        "all associated site works.",
        "not_energy",
    ),
    "bess": (
        "Permission for a 50MW battery energy storage system comprising 20 containerised "
        "battery units, inverters, a substation compound and associated works.",
        "energy",
    ),
}


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def client():
    with httpx.Client() as c:
        yield c


def app_for(description: str) -> Application:
    return Application(
        source="eplanning",
        source_layer="epl_0",
        source_object_id=0,
        application_number="LIVE",
        description=description,
    )


@pytest.mark.parametrize("name", list(FIELD_MAP))
def test_L01_layer_has_mapped_fields(client, name):
    config = FIELD_MAP[name]
    body = client.get(config.url, params={"f": "json"}, timeout=30).json()
    fields = {f["name"] for f in body["fields"]}
    assert set(config.out_fields) <= fields


@pytest.mark.parametrize("name", list(FIELD_MAP))
def test_L02_list_ids_and_fetch_real_application(client, name):
    src = ArcGISSource(FIELD_MAP[name], client)
    ids = src.list_ids()
    assert len(ids) > 20000
    app = next(a for a in (src.fetch(i) for i in ids[-50:]) if a is not None)
    assert app.description and app.application_number


@pytest.mark.parametrize("name", list(KNOWN))
def test_L03_gemini_decision_real(tmp_db, client, settings, name):
    if not settings.gemini_api_key:
        pytest.skip("sem GEMINI_API_KEY")
    d = GeminiDecider(
        slot=1,
        model=settings.model1_id,
        api_key=settings.gemini_api_key,
        client=client,
        tracker=QuotaTracker(tmp_db, settings.model1_id, tz=PACIFIC),
    )
    text, category = KNOWN[name]
    result = d.decide(app_for(text))
    assert result.reason == "ok", result
    assert result.decision.category.value == category


@pytest.mark.parametrize("name", list(KNOWN))
def test_L04_jev_decision_real(tmp_db, client, settings, name):
    if not settings.openrouter_api_key:
        pytest.skip("sem OPENROUTER_API_KEY")
    d = OpenRouterDecider(
        slot=2,
        model=settings.model2_id,
        api_key=settings.openrouter_api_key,
        client=client,
        tracker=QuotaTracker(tmp_db, settings.model2_id, tz=UTC_ZONE),
    )
    text, category = KNOWN[name]
    result = d.decide(app_for(text))
    assert result.reason == "ok", result
    assert result.model.startswith(settings.model2_id)
    assert result.decision.category.value == category


def test_L05_advisor_real(tmp_db, client, settings):
    if not settings.gemini_api_key:
        pytest.skip("sem GEMINI_API_KEY")
    adv = GeminiAdvisor(
        model=settings.advisor_id,
        api_key=settings.gemini_api_key,
        client=client,
        tracker=QuotaTracker(tmp_db, settings.advisor_id, rpm=15, tpm=25000, rpd=1000),
    )
    opinion = adv.opinion(app_for(KNOWN["wind"][0]))
    assert opinion["category"] == "energy"
    assert opinion["text"]
    assert adv.status()["tpm_used"] > 0
