"""The live gwwf payloads for the Millinocket 96-hour bundle and the
Millinocket seasonal template, as dicts the axiom tests mutate into
counterexamples."""

import copy
import json
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parents[1] / "config"
BUNDLE_NAME = "us.me.millinocket.forecast.nws.hourly96"
LOCATION_ALIAS = "us.me.millinocket"


def bundle_dict() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((CONFIG / f"{BUNDLE_NAME}-gw.weather.forecast.bundle.gt-000.json").read_text())
    )


def template_dict() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((CONFIG / f"{LOCATION_ALIAS}-gw.weather.seasonal.template.gt-000.json").read_text())
    )


def forecast_dict() -> dict[str, Any]:
    return copy.deepcopy(
        json.loads((CONFIG / f"{BUNDLE_NAME}-gw.weather.forecast-000.json").read_text())
    )
