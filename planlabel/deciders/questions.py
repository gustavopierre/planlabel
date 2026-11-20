"""Perguntas enviadas aos dois modelos de decisão (SPEC §4.2), geradas da taxonomia do §1.1.

Mudar este texto muda o que os modelos respondem: o teste G-07 guarda um snapshot e
obriga a atualizá-lo de propósito.
"""

from __future__ import annotations

from planlabel.models import Category, Subcategory

HINT = (
    "This is an Irish planning application description. Descriptions rarely say 'wind farm' "
    "or 'solar farm': a wind farm appears as 'N turbines', permission for X years for N "
    "turbines, tip height changes; a solar farm appears as ground-mounted solar PV panels "
    "or arrays, hectares of panels."
)

SUBCATEGORY_DEFINITIONS: dict[Subcategory, str] = {
    Subcategory.HYBRID: (
        "Two or more of wind / solar / battery storage in the same application, "
        "1 MW or more in total."
    ),
    Subcategory.WIND: (
        "Wind turbines or a wind farm (onshore or offshore) of 1 MW or more: installation "
        "of N turbines, permission or extension of permission for N turbines, turbine "
        "replacement (repowering), extensions."
    ),
    Subcategory.SOLAR: "Ground-mounted solar PV installation (solar farm) of 1 MW or more.",
    Subcategory.BESS: "Battery energy storage system as the main development, any size.",
    Subcategory.HYDRO: "Hydroelectric generation, any size.",
    Subcategory.SUBSTATION: (
        "Electricity substation (new or upgraded) serving the grid or generation."
    ),
    Subcategory.ENERGY_SUPPORT: (
        "Construction works that give relevant support to energy projects: national roads, "
        "electricity cables to substations, substation extensions to serve wind or solar "
        "farms (ground-mounted solar). It must be a construction work; the wind or solar "
        "farm itself is wind or solar."
    ),
    Subcategory.LEU: (
        "Large energy user: factories, industrial complexes, housing developments of 200 or "
        "more homes in a single application."
    ),
    Subcategory.DATA_CENTRE: "Data centre.",
    Subcategory.NOT_ENERGY: (
        "Everything else, including fences, car parks, buildings that are not substations, "
        "depots and warehouses, even when they are part of a wind farm, a solar farm or a "
        "large energy user."
    ),
    Subcategory.LOW_ENERGY: (
        "Low energy: wind / solar / hybrid under 1 MW; housing schemes of fewer than 200 "
        "homes; generation from other sources (biomass, diesel, gas, CHP, etc.) of any size; "
        "small substations inside houses, schools or supermarkets; rooftop solar panels; "
        "electric vehicle charging points."
    ),
}

CATEGORY_DEFINITIONS: dict[Category, str] = {
    Category.ENERGY: (
        "Energy development: hybrid, wind, solar, battery storage, hydro, substation, "
        "construction works supporting energy projects, large energy user or data centre."
    ),
    Category.NOT_ENERGY: (
        "Not an energy development, or only low energy (small renewables under 1 MW, fewer "
        "than 200 homes, other generation sources, rooftop solar, EV chargers)."
    ),
}

QUESTIONS: dict[str, dict] = {
    "subcategory": {
        "type": "choice",
        "instructions": (
            f"{HINT} Which subcategory best describes the main purpose of this development?"
        ),
        "criteria": {s.value: SUBCATEGORY_DEFINITIONS[s] for s in Subcategory},
    },
    "category": {
        "type": "choice",
        "instructions": f"{HINT} Is this an energy development?",
        "criteria": {c.value: CATEGORY_DEFINITIONS[c] for c in Category},
    },
}
