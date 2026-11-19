"""Cliente das camadas ArcGIS (SPEC §2). Único lugar onde aparecem nomes de campos."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from planlabel.models import Application

log = logging.getLogger(__name__)


class SourceError(Exception):
    """A fonte não respondeu ou respondeu com erro."""


@dataclass(frozen=True)
class LayerConfig:
    source: str
    source_layer: str
    url: str
    number_field: str
    description_field: str
    authority_field: str
    link_field: str

    @property
    def out_fields(self) -> tuple[str, ...]:
        return (self.number_field, self.description_field, self.authority_field, self.link_field)


FIELD_MAP: dict[str, LayerConfig] = {
    "abp": LayerConfig(
        source="abp",
        source_layer="abp_3",
        url="https://services-eu1.arcgis.com/o56BSnENmD5mYs3j/ArcGIS/rest/services/Cases_2016_Onwards/FeatureServer/3",
        number_field="ABPCASEID",
        description_field="DEVDESC",
        authority_field="PLANINGATY",
        link_field="LINKABPWEB",
    ),
    "eplanning": LayerConfig(
        source="eplanning",
        source_layer="epl_0",
        url="https://services.arcgis.com/NzlPQPKn5QF9v2US/ArcGIS/rest/services/IrishPlanningApplications/FeatureServer/0",
        number_field="ApplicationNumber",
        description_field="DevelopmentDescription",
        authority_field="PlanningAuthority",
        link_field="LinkAppDetails",
    ),
}

TIMEOUT_S = 15.0
BACKOFF_S = (0.5, 1.0, 2.0)  # 1 tentativa + 3 novas tentativas


class ArcGISSource:
    def __init__(
        self,
        config: LayerConfig,
        client: httpx.Client,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl_s: float = 86400,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._client = client
        self._clock = clock
        self._ttl_s = ttl_s
        self._sleep = sleep
        self._ids: list[int] | None = None
        self._ids_at = 0.0

    @property
    def name(self) -> str:
        return self.config.source

    def _query(self, params: dict[str, str]) -> dict:
        params = {**params, "f": "json"}
        last: Exception | None = None
        for attempt in range(len(BACKOFF_S) + 1):
            if attempt:
                self._sleep(BACKOFF_S[attempt - 1])
            try:
                resp = self._client.get(
                    f"{self.config.url}/query", params=params, timeout=TIMEOUT_S
                )
            except httpx.HTTPError as exc:
                last = exc
                continue
            if resp.status_code >= 500:
                last = SourceError(f"HTTP {resp.status_code}")
                continue
            if resp.status_code != 200:
                raise SourceError(f"{self.name}: HTTP {resp.status_code}")
            try:
                body = resp.json()
            except ValueError as exc:
                raise SourceError(f"{self.name}: resposta não é JSON") from exc
            if "error" in body:
                raise SourceError(f"{self.name}: {body['error']}")
            return body
        raise SourceError(
            f"{self.name}: sem resposta após {len(BACKOFF_S) + 1} tentativas"
        ) from last

    RANGE = 250_000  # faixa de OBJECTID por consulta; o ePlanning corta em 400 000 IDs

    def _max_object_id(self) -> int:
        body = self._query(
            {
                "where": "1=1",
                "outStatistics": (
                    '[{"statisticType":"max","onStatisticField":"OBJECTID",'
                    '"outStatisticFieldName":"mx"}]'
                ),
            }
        )
        try:
            return int(body["features"][0]["attributes"]["mx"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise SourceError(f"{self.name}: não consegui ler o maior OBJECTID") from exc

    def list_ids(self) -> list[int]:
        """Todos os OBJECTIDs da camada.

        Acima do limite de transferência o ArcGIS devolve um subconjunto ARBITRÁRIO dos IDs
        (não os menores). Por isso a lista é pedida por faixas fixas de OBJECTID até o maior
        ID da camada; se uma faixa ainda for cortada, ela é dividida ao meio.
        """
        if self._ids is not None and self._clock() - self._ids_at < self._ttl_s:
            return self._ids
        top = self._max_object_id()
        ids: set[int] = set()
        lo, step = 0, self.RANGE
        while lo < top:
            hi = min(lo + step, top)
            body = self._query(
                {"where": f"OBJECTID>{lo} AND OBJECTID<={hi}", "returnIdsOnly": "true"}
            )
            if body.get("exceededTransferLimit"):
                if step == 1:
                    raise SourceError(f"{self.name}: lista de IDs cortada mesmo com faixa 1")
                step = max(1, step // 2)
                continue
            ids.update(body.get("objectIds") or [])
            lo = hi
        self._ids = sorted(ids)
        self._ids_at = self._clock()
        log.info("%s: %d IDs carregados (maior OBJECTID %d)", self.name, len(self._ids), top)
        return self._ids

    def fetch(self, object_id: int) -> Application | None:
        """Um registro; None se não existir ou for inválido (sem número ou descrição)."""
        c = self.config
        body = self._query(
            {
                "objectIds": str(object_id),
                "outFields": ",".join(c.out_fields),
                "returnGeometry": "false",
            }
        )
        features = body.get("features") or []
        if not features:
            return None
        attrs = features[0].get("attributes") or {}
        link = str(attrs.get(c.link_field) or "").strip()
        if not link.lower().startswith(("http://", "https://")):
            link = ""  # link estranho não impede a rotulagem
        try:
            return Application(
                source=c.source,
                source_layer=c.source_layer,
                source_object_id=object_id,
                application_number=attrs.get(c.number_field) or "",
                planning_authority=attrs.get(c.authority_field) or "",
                description=attrs.get(c.description_field) or "",
                application_url=link,
            )
        except ValidationError:
            return None
