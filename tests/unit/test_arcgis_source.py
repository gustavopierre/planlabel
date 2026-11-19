import json

import httpx
import pytest
import respx

from planlabel.sources.arcgis import FIELD_MAP, ArcGISSource, SourceError

ABP = FIELD_MAP["abp"]
EPL = FIELD_MAP["eplanning"]


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def arc(fixtures_dir):
    def load(name):
        return json.loads((fixtures_dir / "arcgis" / name).read_text())

    return load


def make(config, clock=None, ttl=86400):
    sleeps: list[float] = []
    src = ArcGISSource(
        config,
        httpx.Client(),
        clock=clock or Clock(),
        ttl_s=ttl,
        sleep=sleeps.append,
    )
    return src, sleeps


@respx.mock
def test_A01_list_ids_reads_object_ids(arc):
    respx.get(f"{ABP.url}/query").mock(return_value=httpx.Response(200, json=arc("abp_ids.json")))
    src, _ = make(ABP)
    ids = src.list_ids()
    assert ids == sorted(arc("abp_ids.json")["objectIds"])


@respx.mock
def test_A01_list_ids_pages_while_transfer_limit_exceeded():
    calls = []

    def handler(request):
        where = request.url.params["where"]
        calls.append(where)
        if where == "OBJECTID>0":
            return httpx.Response(
                200,
                json={"objectIds": [3, 1, 2], "exceededTransferLimit": True},
            )
        if where == "OBJECTID>3":
            return httpx.Response(200, json={"objectIds": [5, 4]})
        return httpx.Response(500)

    respx.get(f"{EPL.url}/query").mock(side_effect=handler)
    src, _ = make(EPL)
    assert src.list_ids() == [1, 2, 3, 4, 5]
    assert calls == ["OBJECTID>0", "OBJECTID>3"]


@respx.mock
def test_A02_list_ids_cached_within_ttl_and_reloaded_after(arc):
    route = respx.get(f"{ABP.url}/query").mock(
        return_value=httpx.Response(200, json=arc("abp_ids.json"))
    )
    clock = Clock()
    src, _ = make(ABP, clock=clock, ttl=60)
    src.list_ids()
    clock.t += 59
    src.list_ids()
    assert route.call_count == 1
    clock.t += 2
    src.list_ids()
    assert route.call_count == 2


@respx.mock
def test_A03_fetch_builds_query(arc):
    route = respx.get(f"{ABP.url}/query").mock(
        return_value=httpx.Response(200, json=arc("abp_one.json"))
    )
    src, _ = make(ABP)
    src.fetch(100)
    params = route.calls.last.request.url.params
    assert params["objectIds"] == "100"
    assert params["returnGeometry"] == "false"
    assert params["f"] == "json"
    assert set(params["outFields"].split(",")) == {
        "ABPCASEID",
        "DEVDESC",
        "PLANINGATY",
        "LINKABPWEB",
    }


@respx.mock
def test_A04_fetch_maps_fields_per_source(arc):
    respx.get(f"{ABP.url}/query").mock(return_value=httpx.Response(200, json=arc("abp_one.json")))
    respx.get(f"{EPL.url}/query").mock(return_value=httpx.Response(200, json=arc("epl_0_one.json")))
    abp = make(ABP)[0].fetch(100)
    epl = make(EPL)[0].fetch(100)
    assert (abp.source, abp.source_layer, abp.application_number) == ("abp", "abp_3", "300111")
    assert abp.planning_authority == "Cork County Council"
    assert abp.description.startswith("Outline Permission to construct a dwelling")
    assert abp.source_object_id == 100
    assert (epl.source, epl.source_layer, epl.application_number) == (
        "eplanning",
        "epl_0",
        "05/1524",
    )
    assert epl.planning_authority == "Cork County Council"


@respx.mock
def test_A05_fetch_normalizes_text():
    body = {
        "features": [
            {
                "attributes": {
                    "ApplicationNumber": "F19A/0014     ",
                    "DevelopmentDescription": "  two   storey \n extension ",
                    "PlanningAuthority": " Fingal County Council ",
                    "LinkAppDetails": None,
                }
            }
        ]
    }
    respx.get(f"{EPL.url}/query").mock(return_value=httpx.Response(200, json=body))
    app = make(EPL)[0].fetch(1)
    assert app.application_number == "F19A/0014"
    assert app.description == "two storey extension"
    assert app.planning_authority == "Fingal County Council"


@pytest.mark.parametrize(
    "attrs",
    [
        {"ApplicationNumber": "1", "DevelopmentDescription": "   ", "PlanningAuthority": "X"},
        {"ApplicationNumber": None, "DevelopmentDescription": "d", "PlanningAuthority": "X"},
    ],
)
@respx.mock
def test_A06_fetch_invalid_record_returns_none(attrs):
    respx.get(f"{EPL.url}/query").mock(
        return_value=httpx.Response(200, json={"features": [{"attributes": attrs}]})
    )
    assert make(EPL)[0].fetch(1) is None


@respx.mock
def test_A06_fetch_missing_record_returns_none():
    respx.get(f"{EPL.url}/query").mock(return_value=httpx.Response(200, json={"features": []}))
    assert make(EPL)[0].fetch(1) is None


@respx.mock
def test_A07_error_body_with_http_200_is_source_error(arc):
    respx.get(f"{ABP.url}/query").mock(
        return_value=httpx.Response(200, json=arc("arcgis_error.json"))
    )
    with pytest.raises(SourceError):
        make(ABP)[0].fetch(1)


@respx.mock
def test_A08_retries_then_succeeds(arc):
    route = respx.get(f"{ABP.url}/query").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json=arc("abp_one.json")),
        ]
    )
    src, sleeps = make(ABP)
    assert src.fetch(100) is not None
    assert route.call_count == 3
    assert sleeps == [0.5, 1.0]


@respx.mock
def test_A08_four_failures_raise():
    route = respx.get(f"{ABP.url}/query").mock(return_value=httpx.Response(503))
    src, sleeps = make(ABP)
    with pytest.raises(SourceError):
        src.fetch(100)
    assert route.call_count == 4
    assert sleeps == [0.5, 1.0, 2.0]


@respx.mock
def test_A09_timeout_is_source_error():
    respx.get(f"{ABP.url}/query").mock(side_effect=httpx.ReadTimeout("lento"))
    with pytest.raises(SourceError):
        make(ABP)[0].fetch(100)


@respx.mock
def test_A10_link_mapped_http_accepted_and_empty_allowed(arc):
    respx.get(f"{ABP.url}/query").mock(return_value=httpx.Response(200, json=arc("abp_one.json")))
    respx.get(f"{EPL.url}/query").mock(
        side_effect=[
            httpx.Response(200, json=arc("epl_1_one.json")),
            httpx.Response(
                200,
                json={
                    "features": [
                        {
                            "attributes": {
                                "ApplicationNumber": "1",
                                "DevelopmentDescription": "d",
                                "PlanningAuthority": "X",
                                "LinkAppDetails": "",
                            }
                        }
                    ]
                },
            ),
        ]
    )
    assert make(ABP)[0].fetch(100).application_url == "https://www.pleanala.ie/en-ie/case/300111"
    epl = make(EPL)[0]
    assert epl.fetch(100).application_url.startswith("http://www.eplanning.ie/CarlowCC/")
    assert epl.fetch(101).application_url == ""


def test_A10_out_fields_never_request_applicant_data():
    for config in FIELD_MAP.values():
        assert not any(f.lower().startswith("applicant") for f in config.out_fields)
