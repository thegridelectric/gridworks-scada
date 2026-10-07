from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import Quantity, Unit
from gwsproto.property_format import LeftRightDotStr, UtcIso8601Seconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class WeatherChannelGt(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.channel.gt/000"""

    Name: LeftRightDotStr
    DisplayName: Annotated[str, Field(min_length=1)]
    Quantity: Quantity
    Unit: Unit
    LocationAlias: LeftRightDotStr
    EmitPeriodS: PositiveInt
    EmitOffsetS: NonNegativeInt
    Start: UtcIso8601Seconds
    Id: UUID4Str
    TypeName: Literal["gw.weather.channel.gt"] = "gw.weather.channel.gt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """Axiom 1: NameDerivation. Name equals LocationAlias + "." + the
        lowercased Quantity, optionally followed by further segments."""
        derived = f"{self.LocationAlias}.{self.Quantity.value.lower()}"
        if not (self.Name == derived or self.Name.startswith(derived + ".")):
            raise ValueError(
                f"Axiom 1 (NameDerivation) failed: Name must equal {derived!r} "
                f"optionally followed by a variant suffix; got {self.Name!r}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """Axiom 2: EmitOffsetBound. EmitOffsetS is strictly less than EmitPeriodS."""
        if not self.EmitOffsetS < self.EmitPeriodS:
            raise ValueError(
                f"Axiom 2 (EmitOffsetBound) failed: EmitOffsetS ({self.EmitOffsetS}) "
                f"must be strictly less than EmitPeriodS ({self.EmitPeriodS})"
            )
        return self
