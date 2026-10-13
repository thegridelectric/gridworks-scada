from typing import Literal
from pydantic import ConfigDict, StrictFloat, StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import GpmFromHzMethod
from sema_snapshot.sema.enums import HzCalcMethod
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str


class SimPicoFlowModuleComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/sim.pico.flow.module.component.gt/000"""

    component_id: UUID4Str
    device_type: PascalCase
    display_name: str | None = None
    hw_uid: str | None = None
    serial_number: str
    flow_node_name: SpaceheatName
    flow_meter_type: PascalCase
    hz_calc_method: HzCalcMethod
    gpm_from_hz_method: GpmFromHzMethod
    constant_gallons_per_tick: StrictFloat
    send_hz: bool
    send_gallons: bool
    send_tick_lists: bool
    no_flow_ms: StrictInt
    async_capture_threshold_gpm_times100: StrictInt
    publish_empty_ticklist_after_s: StrictInt | None = None
    publish_any_ticklist_after_s: StrictInt | None = None
    publish_ticklist_period_s: StrictInt | None = None
    publish_ticklist_length: StrictInt | None = None
    exp_alpha: StrictFloat | None = None
    cutoff_frequency: StrictFloat | None = None
    sim_life_s: PositiveInt | None = None
    sim_reboot_s: PositiveInt | None = None
    simulates_type_name: Literal["pico.flow.module.component.gt"] = (
        "pico.flow.module.component.gt"
    )
    simulates_version: Literal["001"] = "001"
    type_name: Literal["sim.pico.flow.module.component.gt"] = (
        "sim.pico.flow.module.component.gt"
    )
    version: Literal["000"] = "000"

    model_config = ConfigDict(**(SemaType.model_config | {"extra": "allow"}))

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SimPicoFlowModuleComponentGt":
        """
        Axiom 1: HwUidPattern
        If HwUid is present, it SHALL match the pattern pico_xxxxxx where xxxxxx consists of
        six lowercase hexadecimal characters.
        """
        import re

        if (
            self.hw_uid is not None
            and re.fullmatch(r"pico_[0-9a-f]{6}", self.hw_uid) is None
        ):
            raise ValueError(
                "Axiom 1 (HwUidPattern): HwUid SHALL match pico_xxxxxx "
                "(six lowercase hexadecimal characters)."
            )
        return self
