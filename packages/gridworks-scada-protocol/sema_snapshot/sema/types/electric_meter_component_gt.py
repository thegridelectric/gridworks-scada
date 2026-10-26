from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.electric_meter_channel_config import (
    ElectricMeterChannelConfig,
)


class ElectricMeterComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/electric.meter.component.gt/001"""

    component_id: UUID4Str
    device_type: PascalCase
    config_list: list[ElectricMeterChannelConfig]
    modbus_host: str | None = None
    modbus_port: PositiveInt | None = None
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["electric.meter.component.gt"] = "electric.meter.component.gt"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ElectricMeterComponentGt":
        """
        Axiom 1: ChannelNameUniqueness
        Channel names SHALL be unique across the ConfigList.
        """
        channel_names = [config.channel_name for config in self.config_list]
        if len(channel_names) != len(set(channel_names)):
            raise ValueError(
                "Axiom 1 (ChannelNameUniqueness) failed: channel names must be "
                "unique across the ConfigList."
            )
        return self
