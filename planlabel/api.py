"""API HTTP e montagem do app (SPEC §5)."""

from __future__ import annotations

import logging
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from planlabel.advisor import AdvisorError, AdvisorUnavailable, GeminiAdvisor, NoneAdvisor
from planlabel.config import Settings
from planlabel.models import Label
from planlabel.repository import DuplicateError, Repository
from planlabel.service import Decider, LabelingService, NoApplicationAvailable, UnknownToken
from planlabel.sources.arcgis import FIELD_MAP, ArcGISSource, LayeredSource
from planlabel.sources.registry import Source
from planlabel.translator import TranslationError, Translator, make_translator
from planlabel.usage import PACIFIC, UTC_ZONE, QuotaTracker

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str


class DecideIn(TokenIn):
    slot: Literal[1, 2]


class LabelIn(Label):
    model_config = ConfigDict(frozen=True, extra="forbid")
    token: str


class TranslateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)


def _slot_out(service: LabelingService, slot: int, result=None) -> dict:
    decider = service.deciders[slot]
    out = {"slot": slot, "model": decider.model, "quota": decider.quota()}
    if result is not None:
        out.update(
            model=result.model,
            decision=result.decision.model_dump(mode="json") if result.decision else None,
            reason=result.reason,
        )
    return out


def create_app(
    *,
    repo: Repository,
    sources: Sequence[Source],
    deciders: Mapping[int, Decider],
    advisor=None,
    translator: Translator,
    rng: random.Random | None = None,
) -> FastAPI:
    service = LabelingService(repo, sources, deciders, advisor=advisor, rng=rng)
    app = FastAPI(title="Plan Labeler", docs_url=None, redoc_url=None)
    app.state.service = service

    @app.exception_handler(UnknownToken)
    def _unknown(request: Request, exc: UnknownToken) -> JSONResponse:
        return JSONResponse({"detail": "token desconhecido ou expirado"}, status_code=404)

    @app.exception_handler(DuplicateError)
    def _duplicate(request: Request, exc: DuplicateError) -> JSONResponse:
        return JSONResponse({"detail": "aplicação já rotulada"}, status_code=409)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/api/stats")
    def stats() -> dict:
        return service.counts().model_dump()

    @app.get("/api/next")
    def next_application():
        try:
            pending = service.next_application()
        except NoApplicationAvailable as exc:
            return JSONResponse({"detail": f"Nenhuma fonte respondeu: {exc}"}, status_code=503)
        return {
            "token": pending.token,
            "application": pending.application.public(),
            "stats": service.counts().model_dump(),
            "models": [_slot_out(service, 1), _slot_out(service, 2)],
            "advisor": service.advisor.status(),
        }

    @app.post("/api/decide")
    def decide(body: DecideIn) -> dict:
        result = service.decide(body.token, body.slot)
        return _slot_out(service, body.slot, result)

    @app.post("/api/doubt")
    def doubt(body: TokenIn):
        try:
            opinion = service.doubt(body.token)
        except AdvisorUnavailable as exc:
            return JSONResponse({"advisor": exc.status}, status_code=429)
        except AdvisorError as exc:
            return JSONResponse(
                {"advisor": exc.status or service.advisor.status()}, status_code=502
            )
        return {"opinion": opinion, "advisor": service.advisor.status()}

    @app.get("/api/advisor")
    def advisor_status() -> dict:
        return service.advisor.status()

    @app.post("/api/labels", status_code=201)
    def label(body: LabelIn) -> dict:
        counts = service.confirm(
            body.token, Label(category=body.category, subcategory=body.subcategory)
        )
        return {"stats": counts.model_dump()}

    @app.post("/api/skip", status_code=204)
    def skip(body: TokenIn) -> Response:
        service.skip(body.token)
        return Response(status_code=204)

    @app.post("/api/translate")
    def translate(body: TranslateIn):
        try:
            return {"translation": translator.translate(body.text)}
        except TranslationError as exc:
            log.warning("tradução falhou: %s", exc)
            return JSONResponse({"detail": "tradução indisponível"}, status_code=502)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def _make_decider(slot: int, provider: str, model: str, settings: Settings, repo, client):
    from planlabel.deciders.gemini import GeminiDecider
    from planlabel.deciders.openrouter import OpenRouterDecider

    rpm = settings.model1_rpm if slot == 1 else settings.model2_rpm
    rpd = settings.model1_rpd if slot == 1 else settings.model2_rpd
    if provider == "gemini":
        cls, key, tz = GeminiDecider, settings.gemini_api_key, PACIFIC
    else:
        cls, key, tz = OpenRouterDecider, settings.openrouter_api_key, UTC_ZONE
    tracker = QuotaTracker(repo, model, tz=tz, rpm=rpm, rpd=rpd)
    return cls(
        slot=slot,
        model=model,
        api_key=key,
        client=client,
        tracker=tracker,
        timeout_s=settings.decider_timeout_s,
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    """Monta o app real: fontes ArcGIS, modelos do .env, SQLite e tradutor."""
    settings = settings or Settings()
    repo = Repository(settings.db_path)
    client = httpx.Client(headers={"User-Agent": "planlabel/0.1"})
    sources = [
        ArcGISSource(FIELD_MAP["abp"], client, ttl_s=settings.ids_ttl_s),
        LayeredSource(
            "eplanning",
            [
                ArcGISSource(FIELD_MAP["eplanning"], client, ttl_s=settings.ids_ttl_s),
                ArcGISSource(FIELD_MAP["eplanning_1"], client, ttl_s=settings.ids_ttl_s),
            ],
        ),
    ]
    deciders = {
        1: _make_decider(1, settings.model1_provider, settings.model1_id, settings, repo, client),
        2: _make_decider(2, settings.model2_provider, settings.model2_id, settings, repo, client),
    }
    if settings.gemini_api_key:
        advisor = GeminiAdvisor(
            model=settings.advisor_id,
            api_key=settings.gemini_api_key,
            client=client,
            tracker=QuotaTracker(
                repo,
                settings.advisor_id,
                tz=PACIFIC,
                rpm=settings.advisor_rpm,
                tpm=settings.advisor_tpm,
                rpd=settings.advisor_rpd,
            ),
        )
    else:
        advisor = NoneAdvisor(settings.advisor_id)
    return create_app(
        repo=repo,
        sources=sources,
        deciders=deciders,
        advisor=advisor,
        translator=make_translator(settings.translator),
    )
