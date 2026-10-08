"""Tests gw.weather.seasonal.template.gt type, version 000"""

import pytest
from gwsproto.named_types import WeatherSeasonalTemplateGt

from tests.named_types.weather_fixtures import template_dict


def test_weather_seasonal_template_gt_generated() -> None:
    d = template_dict()
    assert WeatherSeasonalTemplateGt.model_validate(d).model_dump(by_alias=True) == d


def test_gw_weather_seasonal_template_gt_axiom_1_eleven_months() -> None:
    d = template_dict()
    d["TempByMonth"] = d["TempByMonth"][:11]
    with pytest.raises(ValueError, match="Axiom 1"):
        WeatherSeasonalTemplateGt.model_validate(d)
