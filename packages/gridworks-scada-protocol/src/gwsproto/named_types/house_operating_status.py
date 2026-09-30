from typing import Literal, Optional

from pydantic import model_validator
from typing_extensions import Self

from gwsproto import enums
from gwsproto.enums import (
    SeasonalStorageMode,
    ServiceMode,
    StandbyPosture,
    TaValidationState,
    TopState,
)
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class HouseOperatingStatus(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.house.operating.status/000"""

    ScadaAlias: LeftRightDotStr
    ValidationState: TaValidationState
    Standby: bool
    StandbyPosture: StandbyPosture
    SeasonalStorageMode: SeasonalStorageMode
    ServiceMode: ServiceMode
    AcceptsDispatch: bool
    # The class attribute shadows the enum name inside the class body, so the
    # annotation goes through the module.
    DispatchRefusalReason: Optional[enums.DispatchRefusalReason] = None
    TopState: TopState
    LtnDispatching: bool
    UnixMs: UTCMilliseconds
    TypeName: Literal["gw.house.operating.status"] = "gw.house.operating.status"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: RefusalReasonPresence.
        DispatchRefusalReason SHALL be present if and only if
        AcceptsDispatch is false.
        """
        if self.AcceptsDispatch == (self.DispatchRefusalReason is not None):
            raise ValueError(
                "Axiom 1 (RefusalReasonPresence) failed: DispatchRefusalReason is "
                "present iff AcceptsDispatch is false; got AcceptsDispatch "
                f"{self.AcceptsDispatch}, DispatchRefusalReason {self.DispatchRefusalReason}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: StandbyRefusesDispatch.
        If Standby is true, AcceptsDispatch SHALL be false and
        DispatchRefusalReason SHALL be Standby.
        """
        if self.Standby and (
            self.AcceptsDispatch
            or self.DispatchRefusalReason is not enums.DispatchRefusalReason.Standby
        ):
            raise ValueError(
                "Axiom 2 (StandbyRefusesDispatch) failed: Standby requires "
                "AcceptsDispatch false and DispatchRefusalReason Standby; got "
                f"AcceptsDispatch {self.AcceptsDispatch}, "
                f"DispatchRefusalReason {self.DispatchRefusalReason}"
            )
        return self
