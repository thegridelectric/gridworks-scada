from typing import Literal, Optional

from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import TelemetryName
from gwsproto.named_types.i2c_adc_config import I2cAdcConfig
from gwsproto.named_types.i2c_bus import I2cBus
from gwsproto.named_types.i2c_dac_config import I2cDacConfig
from gwsproto.named_types.i2c_relay_config import I2cRelayConfig
from gwsproto.named_types.i2c_thermistor_interface_config import (
    I2cThermistorInterfaceConfig,
)
from gwsproto.named_types.native_gpio_pin import NativeGpioPin
from gwsproto.property_format import PascalCase


class ScadaDeviceTypeGt(BaseModel):
    """Sema: https://schemas.electricity.works/types/gw1.scada.device.type.gt/000"""

    DeviceType: PascalCase
    DisplayName: Optional[str] = None
    MinPollPeriodMs: Optional[PositiveInt] = None
    BusList: list[I2cBus] = []
    TelemetryNameList: list[TelemetryName] = []
    NativeGpioInputs: list[NativeGpioPin] = []
    NativeGpioOutputs: list[NativeGpioPin] = []
    I2cRelays: list[I2cRelayConfig] = []
    CtAdc: Optional[I2cAdcConfig] = None
    ThermistorAdcs: list[I2cThermistorInterfaceConfig] = []
    Dacs: list[I2cDacConfig] = []
    TypeName: Literal["gw1.scada.device.type.gt"] = "gw1.scada.device.type.gt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: BusMembership. Every I2cBus referenced by an entry in I2cRelays,
        CtAdc, ThermistorAdcs, or Dacs SHALL appear as a Name in BusList.
        """
        bus_names = {bus.Name for bus in self.BusList}
        referenced: set[str] = {relay.I2cBus for relay in self.I2cRelays}
        referenced |= {ta.I2cBus for ta in self.ThermistorAdcs}
        referenced |= {dac.I2cBus for dac in self.Dacs}
        if self.CtAdc is not None:
            referenced.add(self.CtAdc.I2cBus)
        missing = referenced - bus_names
        if missing:
            raise ValueError(
                f"Axiom 1 (BusMembership) failed: I2cBus name(s) {sorted(missing)} "
                f"not in BusList {sorted(bus_names)}."
            )
        return self
