from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import DispatchRefusalReason
from sema_snapshot.sema.enums import SeasonalStorageMode
from sema_snapshot.sema.enums import ServiceMode
from sema_snapshot.sema.enums import StandbyPosture
from sema_snapshot.sema.enums import TaValidationState
from sema_snapshot.sema.enums import TopState
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds


class HouseOperatingStatus(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.house.operating.status/000"""

    scada_alias: LeftRightDot
    validation_state: TaValidationState
    standby: bool
    standby_posture: StandbyPosture
    seasonal_storage_mode: SeasonalStorageMode
    service_mode: ServiceMode
    accepts_dispatch: bool
    dispatch_refusal_reason: DispatchRefusalReason | None = None
    top_state: TopState
    scada_blind: bool
    ltn_dispatching: bool
    created_ms: UTCMilliseconds
    type_name: Literal["gw.house.operating.status"] = "gw.house.operating.status"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "HouseOperatingStatus":
        """
        Axiom 1: RefusalReasonPresence
        DispatchRefusalReason SHALL be present if and only if AcceptsDispatch is false.
        """
        if self.accepts_dispatch and self.dispatch_refusal_reason is not None:
            raise ValueError(
                "Axiom 1 (RefusalReasonPresence) failed: AcceptsDispatch true "
                "forbids DispatchRefusalReason."
            )
        if not self.accepts_dispatch and self.dispatch_refusal_reason is None:
            raise ValueError(
                "Axiom 1 (RefusalReasonPresence) failed: AcceptsDispatch false "
                "requires DispatchRefusalReason."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "HouseOperatingStatus":
        """
        Axiom 2: StandbyRefusesDispatch
        If Standby is true, AcceptsDispatch SHALL be false and DispatchRefusalReason SHALL
        be OperatorHold.
        """
        if self.standby and (
            self.accepts_dispatch
            or self.dispatch_refusal_reason is not DispatchRefusalReason.OperatorHold
        ):
            raise ValueError(
                "Axiom 2 (StandbyRefusesDispatch) failed: Standby requires "
                "AcceptsDispatch false with DispatchRefusalReason OperatorHold."
            )
        return self
