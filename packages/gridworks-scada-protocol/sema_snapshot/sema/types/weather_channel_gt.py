from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import Quantity
from sema_snapshot.sema.enums import Unit
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import LowercaseToken
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.property_format import UtcIso8601Seconds


class WeatherChannelGt(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.weather.channel.gt/002"""

    name: LeftRightDot
    display_name: NonEmptyString
    quantity: Quantity
    unit: Unit
    station_alias: LowercaseToken
    emit_period_s: PositiveInt
    emit_offset_s: NonNegativeInt
    start: UtcIso8601Seconds
    id: UUID4Str
    type_name: Literal["gw.weather.channel.gt"] = "gw.weather.channel.gt"
    version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "WeatherChannelGt":
        """
        Axiom 1: NameDerivation
        Name SHALL equal StationAlias + "." + the lowercased Quantity value, optionally
        followed by "." and one or more further segments (a variant suffix for a
        semantically different series from the same station, never acquisition detail).
        """
        derived = f"{self.station_alias}.{self.quantity.value.lower()}"
        if not (self.name == derived or self.name.startswith(derived + ".")):
            raise ValueError(
                "Axiom 1 (NameDerivation) failed: Name must equal "
                f"StationAlias + '.' + lowercased Quantity ('{derived}'), "
                f"optionally followed by a variant suffix; got '{self.name}'."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "WeatherChannelGt":
        """
        Axiom 2: EmitOffsetBound
        EmitOffsetS SHALL be strictly less than EmitPeriodS.
        """
        if not self.emit_offset_s < self.emit_period_s:
            raise ValueError(
                "Axiom 2 (EmitOffsetBound) failed: EmitOffsetS "
                f"({self.emit_offset_s}) must be strictly less than "
                f"EmitPeriodS ({self.emit_period_s})."
            )
        return self
