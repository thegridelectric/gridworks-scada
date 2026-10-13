from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import I2cAdcType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveFloat
from sema_snapshot.sema.property_format import PositiveInt


class I2cThermistorInterfaceCapability(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.interface.capability/000"""

    name: PascalCase
    i2c_bus: PascalCase
    i2c_address: NonNegativeInt
    adc_type: I2cAdcType
    supported_data_rates_sps: list[PositiveInt]
    adc_reference_volts: PositiveFloat
    series_resistance_k_ohms: PositiveFloat
    type_name: Literal["i2c.thermistor.interface.capability"] = (
        "i2c.thermistor.interface.capability"
    )
    version: Literal["000"] = "000"
