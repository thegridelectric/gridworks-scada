from typing import Literal, Self
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import CirculatorRole
from sema_snapshot.sema.property_format import SpaceheatName


class Circulator(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.circulator/000"""

    pump_node_name: SpaceheatName
    role: CirculatorRole
    running_channel_name: SpaceheatName
    flow_channel_name: SpaceheatName | None = None
    power_channel_name: SpaceheatName | None = None
    ct_channel_name: SpaceheatName | None = None
    zero_ten_node_name: SpaceheatName | None = None
    type_name: Literal["gw.circulator"] = "gw.circulator"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: InputDeclared
        At least one of PowerChannelName and CtChannelName SHALL be present.
        """
        if self.power_channel_name is None and self.ct_channel_name is None:
            raise ValueError(
                "Axiom 1 (InputDeclared) failed: circulator "
                f"{self.pump_node_name!r} declares neither PowerChannelName nor "
                "CtChannelName."
            )
        return self
