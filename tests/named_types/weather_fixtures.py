"""The live gwwf payloads for the Millinocket moose bundle and the
Millinocket seasonal template, with a forecast message in the live shape,
as dicts the axiom tests mutate into counterexamples."""

import copy
import json
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parents[1] / "config"
BUNDLE_NAME = "us.me.millinocket.moose"
LOCATION_ALIAS = "us.me.millinocket"


def bundle_dict() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((CONFIG / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-002.json").read_text())
    )


def binding_dict(quantity: str) -> dict[str, Any]:
    """The bundle's binding whose observed channel is `quantity`."""
    return next(b for b in bundle_dict()["BindingList"] if b["ObservationChannel"]["Quantity"] == quantity)


def template_dict() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((CONFIG / f"{LOCATION_ALIAS}-gw.weather.seasonal.template.gt-000.json").read_text())
    )


def forecast_dict() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((CONFIG / f"{BUNDLE_NAME}-gw.weather.forecast-001.json").read_text())
    )


def series_dict(quantity: str) -> dict[str, Any]:
    """The forecast message's series of `quantity`."""
    return next(s for s in forecast_dict()["SeriesList"] if s["Quantity"] == quantity)
