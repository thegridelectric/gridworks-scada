from typing import Literal
from pydantic import StrictFloat, StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import GpmFromHzMethod
from sema_snapshot.sema.enums import HzCalcMethod
from sema_snapshot.sema.enums import PicoBoardVariant
from sema_snapshot.sema.property_format import FirmwareCommit
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str


class PicoFlowModuleComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/pico.flow.module.component.gt/001"""

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
    pico_board_variant: PicoBoardVariant
    micropython_version: str | None = None
    firmware_commit: FirmwareCommit | None = None
    type_name: Literal["pico.flow.module.component.gt"] = (
        "pico.flow.module.component.gt"
    )
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "PicoFlowModuleComponentGt":
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
