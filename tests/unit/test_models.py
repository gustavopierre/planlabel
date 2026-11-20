import json

import pytest
from pydantic import ValidationError

from planlabel.models import (
    CATEGORY_OF,
    Application,
    Category,
    Decision,
    Label,
    Subcategory,
)

ENERGY_SUBS = [
    "hybrid",
    "wind",
    "solar",
    "bess",
    "hydro",
    "substation",
    "energy_support",
    "leu",
    "data_centre",
]
NOT_ENERGY_SUBS = ["not_energy", "low_energy"]


def sub_probs(**over: float) -> dict[str, float]:
    probs = dict.fromkeys(ENERGY_SUBS + NOT_ENERGY_SUBS, 0.0)
    probs.update(over)
    return probs


def make_app(**over) -> dict:
    data = {
        "source": "abp",
        "source_layer": "abp_3",
        "source_object_id": 1,
        "application_number": "300111",
        "planning_authority": "Cork County Council",
        "description": "Construct a dwelling",
        "application_url": "https://www.pleanala.ie/en-ie/case/300111",
    }
    data.update(over)
    return data


@pytest.mark.parametrize("sub", ENERGY_SUBS + NOT_ENERGY_SUBS)
def test_M01_label_valid_for_each_subcategory_with_its_category(sub):
    category = "energy" if sub in ENERGY_SUBS else "not_energy"
    label = Label(category=category, subcategory=sub)
    assert label.category == Category(category)
    assert label.subcategory == Subcategory(sub)
    assert CATEGORY_OF[Subcategory(sub)] == Category(category)


def test_M01_canonical_order_and_mapping_cover_all_subcategories():
    assert [s.value for s in Subcategory] == ENERGY_SUBS + NOT_ENERGY_SUBS
    assert set(CATEGORY_OF) == set(Subcategory)


@pytest.mark.parametrize(
    "data",
    [
        {"category": "energy", "subcategory": "nuclear"},
        {"category": "nuclear", "subcategory": "wind"},
        {"category": "energy"},
        {"subcategory": "wind"},
    ],
)
def test_M02_invalid_or_missing_values_rejected(data):
    with pytest.raises(ValidationError):
        Label(**data)


@pytest.mark.parametrize(
    ("category", "sub"),
    [("energy", "low_energy"), ("energy", "not_energy"), ("not_energy", "wind")],
)
def test_M03_incoherent_human_label_rejected(category, sub):
    with pytest.raises(ValidationError):
        Label(category=category, subcategory=sub)


def test_M03_label_rejects_extra_fields():
    with pytest.raises(ValidationError):
        Label(category="energy", subcategory="wind", m1_decision="{}")


def test_M04_decision_from_api_derives_choices_and_percentages():
    d = Decision.from_api(
        model="gemini-decision-1",
        subcategory_probabilities=sub_probs(wind=0.82, hybrid=0.04, substation=0.14),
        subcategory_choice="wind",
        category_probabilities={"energy": 0.91, "not_energy": 0.09},
        category_choice="energy",
    )
    assert d.subcategory == Subcategory.WIND
    assert d.subcategory_pct == 82
    assert d.category == Category.ENERGY
    assert d.category_pct == 91
    assert d.consistent is True
    assert sum(d.subcategory_distribution.values()) == 100
    assert sum(d.category_distribution.values()) == 100
    assert list(d.subcategory_distribution) == ENERGY_SUBS + NOT_ENERGY_SUBS
    assert json.loads(d.stored()) == {
        "category": "energy",
        "category_pct": 91,
        "subcategory": "wind",
        "subcategory_pct": 82,
    }


def test_M05_probabilities_converted_with_largest_remainder():
    # 0.333.. × 3 → 33 + 33 + 34 = 100
    probs = sub_probs(wind=1 / 3, solar=1 / 3, bess=1 / 3)
    d = Decision.from_api(
        model="m",
        subcategory_probabilities=probs,
        subcategory_choice="wind",
        category_probabilities={"energy": 0.995, "not_energy": 0.0},
        category_choice="energy",
    )
    dist = d.subcategory_distribution
    assert sum(dist.values()) == 100
    assert sorted([dist[Subcategory.WIND], dist[Subcategory.SOLAR], dist[Subcategory.BESS]]) == [
        33,
        33,
        34,
    ]
    assert d.category_distribution == {Category.ENERGY: 100, Category.NOT_ENERGY: 0}


@pytest.mark.parametrize(
    "probs",
    [
        sub_probs(wind=0.8),  # soma 0,8
        {k: v for k, v in sub_probs(wind=1.0).items() if k != "leu"},  # chave faltando
        {**sub_probs(wind=1.0), "nuclear": 0.0},  # chave extra
        sub_probs(wind=1.2, solar=-0.2),  # fora de 0..1
    ],
)
def test_M05_invalid_probabilities_rejected(probs):
    with pytest.raises(ValidationError):
        Decision.from_api(
            model="m",
            subcategory_probabilities=probs,
            subcategory_choice="wind",
            category_probabilities={"energy": 1.0, "not_energy": 0.0},
            category_choice="energy",
        )


def test_M05_unknown_choice_rejected():
    with pytest.raises(ValidationError):
        Decision.from_api(
            model="m",
            subcategory_probabilities=sub_probs(wind=1.0),
            subcategory_choice="nuclear",
            category_probabilities={"energy": 1.0, "not_energy": 0.0},
            category_choice="energy",
        )


@pytest.mark.parametrize(
    "over",
    [
        {"application_number": "  "},
        {"description": ""},
        {"description": "   \n "},
        {"application_url": "ftp://x"},
        {"application_url": "javascript:alert(1)"},
    ],
)
def test_M06_invalid_application_rejected(over):
    with pytest.raises(ValidationError):
        Application(**make_app(**over))


def test_M06_application_normalizes_and_accepts_http_or_empty_url():
    app = Application(
        **make_app(
            application_number="F19A/0014     ",
            description="  two   storey\n extension ",
            application_url="http://www.eplanning.ie/CarlowCC/AppFileRefDetails/19114/0",
        )
    )
    assert app.application_number == "F19A/0014"
    assert app.description == "two storey extension"
    assert Application(**make_app(application_url="")).application_url == ""


def test_M07_choice_comes_from_api_even_when_rounding_ties():
    d = Decision.from_api(
        model="m",
        subcategory_probabilities=sub_probs(wind=0.501, hybrid=0.499),
        subcategory_choice="wind",
        category_probabilities={"energy": 1.0, "not_energy": 0.0},
        category_choice="energy",
    )
    assert d.subcategory_distribution[Subcategory.WIND] == 50
    assert d.subcategory_distribution[Subcategory.HYBRID] == 50
    assert d.subcategory == Subcategory.WIND


def test_M08_contradictory_decision_is_valid_and_preserved():
    d = Decision.from_api(
        model="m",
        subcategory_probabilities=sub_probs(wind=0.6, not_energy=0.4),
        subcategory_choice="wind",
        category_probabilities={"energy": 0.45, "not_energy": 0.55},
        category_choice="not_energy",
    )
    assert d.consistent is False
    assert d.subcategory == Subcategory.WIND
    assert d.category == Category.NOT_ENERGY
    assert json.loads(d.stored())["category"] == "not_energy"
