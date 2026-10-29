from typing import Literal, Optional

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import CirculatorRole
from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class Circulator(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.circulator/000"""

    PumpNodeName: SpaceheatName
    Role: CirculatorRole
    RunningChannelName: SpaceheatName
    FlowChannelName: Optional[SpaceheatName] = None
    PowerChannelName: Optional[SpaceheatName] = None
    CtChannelName: Optional[SpaceheatName] = None
    ZeroTenNodeName: Optional[SpaceheatName] = None
    TypeName: Literal["gw.circulator"] = "gw.circulator"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: InputDeclared
        At least one of PowerChannelName and CtChannelName SHALL be present.
        """
        if self.PowerChannelName is None and self.CtChannelName is None:
            raise ValueError(
                "Axiom 1 (InputDeclared) failed: circulator "
                f"{self.PumpNodeName!r} declares neither PowerChannelName nor "
                "CtChannelName."
            )
        return self
