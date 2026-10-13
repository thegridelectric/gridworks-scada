from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import GpmFromHzMethod
from sema_snapshot.sema.enums import HzCalcMethod
from sema_snapshot.sema.enums import PicoBoardVariant
from sema_snapshot.sema.enums import TempCalcMethod
from sema_snapshot.sema.property_format import FirmwareCommit
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveFloat
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str


class PicoBtuMeterComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/pico.btu.meter.component.gt/000"""

    component_id: UUID4Str
    device_type: PascalCase
    serial_number: str
    flow_channel_name: SpaceheatName
    hot_channel_name: SpaceheatName
    cold_channel_name: SpaceheatName
    ct_channel_name: SpaceheatName | None = None
    read_ct_voltage: bool
    send_hz: bool
    flow_meter_type: PascalCase
    hz_calc_method: HzCalcMethod
    temp_calc_method: TempCalcMethod
    gpm_from_hz_method: GpmFromHzMethod
    thermistor_beta: StrictInt
    gallons_per_pulse: PositiveFloat
    async_capture_delta_gpm_x100: StrictInt
    async_capture_delta_celsius_x100: StrictInt
    async_capture_delta_ct_volts_x100: StrictInt | None = None
    display_name: str | None = None
    hw_uid: str | None = None
    pico_board_variant: PicoBoardVariant
    micropython_version: str | None = None
    firmware_commit: FirmwareCommit | None = None
    type_name: Literal["pico.btu.meter.component.gt"] = "pico.btu.meter.component.gt"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "PicoBtuMeterComponentGt":
        """
        Axiom 1: ReadCtVoltageIffCtVoltsDelta
        ReadCtVoltage SHALL be true iff AsyncCaptureDeltaCtVoltsX100 is present.
        """
        if bool(self.read_ct_voltage) != (
            self.async_capture_delta_ct_volts_x100 is not None
        ):
            raise ValueError(
                "Axiom 1: ReadCtVoltage must be true exactly when "
                "AsyncCaptureDeltaCtVoltsX100 is present."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "PicoBtuMeterComponentGt":
        """
        Axiom 2: ReadCtVoltageIffCtChannelName
        ReadCtVoltage SHALL be true iff CtChannelName is present.
        """
        if bool(self.read_ct_voltage) != (self.ct_channel_name is not None):
            raise ValueError(
                "Axiom 2: ReadCtVoltage must be true exactly when "
                "CtChannelName is present."
            )
        return self
