import time
from typing import Any, List, Literal

from gwsproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from pydantic import model_validator
from typing_extensions import Self


class HeatingForecast(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/heating.forecast/000"""

    FromGNodeAlias: LeftRightDotStr
    Time: List[UTCSeconds]
    AvgPowerKw: List[float]
    RswtF: List[float]
    RswtDeltaTF: List[float]
    WeatherUid: UUID4Str
    ForecastCreatedS: UTCSeconds
    TypeName: Literal["heating.forecast"] = "heating.forecast"
    Version: Literal["000"] = "000"

    def __init__(self, **data: Any) -> None:
        # Construction stamps the clock; decoding requires the field on the wire.
        data.setdefault("ForecastCreatedS", int(time.time()))
        super().__init__(**data)

    # Pydantic routes validation through a custom __init__ unless it carries
    # this marker; with it, only direct construction runs the defaulting.
    __init__.__pydantic_base_init__ = True  # type: ignore[attr-defined]

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Length of all hte lists must be the same.

        """
        if len(self.AvgPowerKw) != len(self.Time):
            raise ValueError(
                f"self.AvgPowerKw should be a list of length {len(self.Time)}!"
            )
        if len(self.RswtF) != len(self.Time):
            raise ValueError(f"self.RswtF should be a list of length {len(self.Time)}!")
        if len(self.RswtDeltaTF) != len(self.Time):
            raise ValueError(
                f"self.RswtDeltaTFshould be a list of length {len(self.Time)}!"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ForecastCreatedS is less than the first second in Time
        """
        if len(self.Time) > 0:
            if self.ForecastCreatedS > self.Time[0]:
                raise ValueError(
                    "Forecast should not be created after beginning of forecasted time!"
                )

        return self
