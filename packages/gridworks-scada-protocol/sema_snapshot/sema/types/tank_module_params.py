from typing import Literal
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import PicoBoardVariant
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName


class TankModuleParams(SemaType):
    """Sema: https://schemas.electricity.works/types/tank.module.params/200"""

    hw_uid: str
    actor_node_name: SpaceheatName
    pico_a_b: str | None = None
    capture_period_s: PositiveInt
    samples: PositiveInt
    num_sample_averages: PositiveInt
    async_capture_delta_micro_volts: PositiveInt
    capture_offset_s: StrictFloat | None = None
    pico_board_variant: PicoBoardVariant
    micropython_version: str
    type_name: Literal["tank.module.params"] = "tank.module.params"
    version: Literal["200"] = "200"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "TankModuleParams":
        """
        Axiom 1: PicoABIsAOrB
        If PicoAB is present it SHALL be "a" or "b".
        """
        if self.pico_a_b is not None and self.pico_a_b not in ("a", "b"):
            raise ValueError(
                f"Axiom 1: If PicoAB is present it SHALL be a or b, not {self.pico_a_b!r}"
            )
        return self
