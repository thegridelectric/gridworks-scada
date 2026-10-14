"""Tests gw.weather.seasonal.template.gt type, version 000"""

from gwsproto.named_types import WeatherSeasonalTemplateGt

from tests.named_types.weather_fixtures import template_dict
from tests.named_types.sema_oracle import assert_refused


def test_gw_weather_seasonal_template_gt_axiom_1_eleven_months() -> None:
    d = template_dict()
    d["TempByMonth"] = d["TempByMonth"][:11]
    assert_refused(WeatherSeasonalTemplateGt, d, match="Axiom 1")
