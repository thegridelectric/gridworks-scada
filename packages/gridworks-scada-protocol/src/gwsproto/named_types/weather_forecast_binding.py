from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.named_types.weather_channel_gt import WeatherChannelGt
from gwsproto.named_types.weather_forecast_channel_gt import WeatherForecastChannelGt
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WeatherForecastBinding(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.forecast.binding/000"""

    ForecastChannel: WeatherForecastChannelGt
    ObservationChannel: WeatherChannelGt
    TypeName: Literal["gw.weather.forecast.binding"] = "gw.weather.forecast.binding"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: TargetBinding. ForecastChannel.TargetChannelName equals
        ObservationChannel.Name."""
        if self.ForecastChannel.TargetChannelName != self.ObservationChannel.Name:
            raise ValueError(
                "Axiom 1 (TargetBinding) failed: ForecastChannel.TargetChannelName "
                f"({self.ForecastChannel.TargetChannelName!r}) must equal "
                f"ObservationChannel.Name ({self.ObservationChannel.Name!r})"
            )
        return self
