"""A-11: a fonte ePlanning junta as camadas 0 e 1 sem virar duas vezes no rodízio."""

import json

import httpx
import pytest
import respx

from planlabel.sources.arcgis import FIELD_MAP, ArcGISSource, LayeredSource, SourceError
from tests.conftest import make_application


class Layer:
    def __init__(self, layer, ids, fail=False):
        self.name = "eplanning"
        self.layer = layer
        self.ids = ids
        self.fail = fail
        self.list_calls = 0
        self.fetched: list[int] = []

    def list_ids(self):
        self.list_calls += 1
        if self.fail:
            raise SourceError("fora do ar")
        return self.ids

    def fetch(self, object_id):
        self.fetched.append(object_id)
        return make_application(
            "eplanning", object_id, source_layer=self.layer, application_number=str(object_id)
        )


def test_A11_merges_layers_without_id_collision():
    l0, l1 = Layer("epl_0", [1, 2, 3]), Layer("epl_1", [2, 3, 4])
    src = LayeredSource("eplanning", [l0, l1])
    ids = src.list_ids()
    assert src.name == "eplanning"
    assert len(ids) == 6 and len(set(ids)) == 6
    assert not isinstance(ids, list)  # visão, sem copiar 1 milhão de IDs
    got = sorted((a.source_layer, a.source_object_id) for a in map(src.fetch, ids))
    assert got == [
        ("epl_0", 1),
        ("epl_0", 2),
        ("epl_0", 3),
        ("epl_1", 2),
        ("epl_1", 3),
        ("epl_1", 4),
    ]


def test_A11_merged_list_reused_while_layers_unchanged():
    l0, l1 = Layer("epl_0", [1, 2]), Layer("epl_1", [5])
    src = LayeredSource("eplanning", [l0, l1])
    assert src.list_ids() is src.list_ids()
    l1.ids = [5, 6]
    assert len(src.list_ids()) == 4


def test_A11_one_layer_down_other_still_serves():
    l0, l1 = Layer("epl_0", [1, 2], fail=True), Layer("epl_1", [7])
    src = LayeredSource("eplanning", [l0, l1])
    ids = src.list_ids()
    assert [src.fetch(i).source_layer for i in ids] == ["epl_1"]
    l1.fail = True
    with pytest.raises(SourceError):
        src.list_ids()


def test_A11_layers_must_share_source_name():
    with pytest.raises(ValueError):
        LayeredSource("eplanning", [Layer("epl_0", [1]), type("X", (), {"name": "abp"})()])


@respx.mock
def test_A11_layer1_field_map_and_no_applicant_fields(fixtures_dir):
    cfg = FIELD_MAP["eplanning_1"]
    assert (cfg.source, cfg.source_layer) == ("eplanning", "epl_1")
    assert cfg.url.endswith("/IrishPlanningApplications/FeatureServer/1")
    assert not any(f.startswith("Applicant") for f in cfg.out_fields)
    one = json.loads((fixtures_dir / "arcgis" / "epl_1_one.json").read_text())
    respx.get(f"{cfg.url}/query").mock(return_value=httpx.Response(200, json=one))
    app = ArcGISSource(cfg, httpx.Client(), sleep=lambda s: None).fetch(42)
    assert (app.source, app.source_layer, app.source_object_id) == ("eplanning", "epl_1", 42)
    assert app.application_number and app.description


def test_A11_ids_view_indexing_and_random_choice():
    import random

    src = LayeredSource("eplanning", [Layer("epl_0", [10, 20]), Layer("epl_1", [30])])
    ids = src.list_ids()
    assert list(ids) == [20, 40, 61]
    assert ids[-1] == 61 and ids[0:2] == [20, 40]
    with pytest.raises(IndexError):
        ids[3]
    assert random.Random(3).choice(ids) in {20, 40, 61}
