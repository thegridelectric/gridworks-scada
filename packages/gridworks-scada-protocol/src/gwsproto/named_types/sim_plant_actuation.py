from typing import Literal

from gwsproto.enums import ChangeRelayPin
from gwsproto.property_format import (
    SpaceheatName,
    UtcIso8601Millis,
    UTCMilliseconds,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SimPlantActuation(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/sim.plant.actuation/000"""

    RelayName: SpaceheatName
    Action: ChangeRelayPin
    ActuationTimeUnixMs: UTCMilliseconds
    ActualTimeUtc: UtcIso8601Millis
    TypeName: Literal["sim.plant.actuation"] = "sim.plant.actuation"
    Version: Literal["000"] = "000"
