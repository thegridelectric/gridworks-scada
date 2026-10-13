from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TempCalcMethod
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.i2c_thermistor_channel_config import (
    I2cThermistorChannelConfig,
)


class I2cThermistorReaderComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.reader.component.gt/000"""

    component_id: UUID4Str
    board_component_id: UUID4Str
    config_list: list[I2cThermistorChannelConfig]
    display_name: str | None = None
    hw_uid: str | None = None
    adc_name: PascalCase
    data_rate_sps: PositiveInt
    temp_calc_method: TempCalcMethod
    type_name: Literal["i2c.thermistor.reader.component.gt"] = (
        "i2c.thermistor.reader.component.gt"
    )
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cThermistorReaderComponentGt":
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
