from typing import Literal
from pydantic import StrictFloat, StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import PicoBoardVariant
from sema_snapshot.sema.property_format import PositiveFloat
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName


class AsyncBtuParams(SemaType):
    """Sema: https://schemas.electricity.works/types/async.btu.params/100"""

    hw_uid: str
    actor_node_name: SpaceheatName
    flow_channel_name: SpaceheatName
    send_hz: bool
    read_ct_voltage: bool
    hot_channel_name: SpaceheatName
    cold_channel_name: SpaceheatName
    ct_channel_name: SpaceheatName | None = None
    thermistor_beta: StrictInt | None = None
    capture_period_s: PositiveInt
    gallons_per_pulse: PositiveFloat
    async_capture_delta_gpm_x100: PositiveInt
    async_capture_delta_celsius_x100: PositiveInt
    async_capture_delta_ct_volts_x100: PositiveInt | None = None
    capture_offset_s: StrictFloat | None = None
    pico_board_variant: PicoBoardVariant
    micropython_version: str
    type_name: Literal["async.btu.params"] = "async.btu.params"
    version: Literal["100"] = "100"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "AsyncBtuParams":
        """
        Axiom 1: ReadCtVoltageIffCtChannelName
        ReadCtVoltage is true iff CtChannelName is present.
        """
        truthy = [
            bool(self.read_ct_voltage),
            self.ct_channel_name is not None,
        ]
        if not (all(truthy) or not any(truthy)):
            raise ValueError(
                "Axiom 1: ReadCtVoltage and CtChannelName must either BOTH be "
                "set/present (True/nonnull) or BOTH be unset/absent."
            )
        return self
