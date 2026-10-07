from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto import enums
from gwsproto.enums import ServiceMode, StandbyPosture
from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.named_types.cop_curve import CopCurve
from gwsproto.named_types.heating_curve import HeatingCurve
from gwsproto.named_types.house0_family_params import House0FamilyParams
from gwsproto.named_types.nolan_family_params import NolanFamilyParams
from gwsproto.named_types.tou_tariff import TouTariff
from gwsproto.named_types.zero_ten_power_on import ZeroTenPowerOn
from gwsproto.property_format import LeftRightDotStr, SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class OperationalParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.operational.params/000"""

    ScadaAlias: LeftRightDotStr
    FamilyParams: Annotated[
        Union[House0FamilyParams, NolanFamilyParams],
        Field(discriminator="TypeName"),
    ]
    CaptureTuningList: List[CaptureTuning]
    ZeroTenPowerOnList: List[ZeroTenPowerOn]
    Standby: bool
    StandbyPosture: StandbyPosture
    EnergizedStandbyRelays: List[SpaceheatName]
    ServiceMode: ServiceMode
    AcceptsDispatch: bool
    # The class attribute shadows the enum name inside the class body, so the
    # annotation goes through the module.
    DispatchRefusalReason: Optional[enums.DispatchRefusalReason] = None
    CopCurve: CopCurve
    HeatingCurve: HeatingCurve
    HpTurnOnMinutes: PositiveInt
    HpMaxKwEl: PositiveFloat
    LoadOverestimationPercent: NonNegativeInt
    UsesBackupWhenCold: bool
    HorizonHours: PositiveInt
    WeatherBundleName: LeftRightDotStr
    Tariff: TouTariff
    TypeName: Literal["gw.operational.params"] = "gw.operational.params"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: CaptureTuningChannelUniqueness.
        ChannelName is unique across the CaptureTuningList.
        """
        channel_names = [ct.ChannelName for ct in self.CaptureTuningList]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted(
                {n for n in channel_names if channel_names.count(n) > 1}
            )
            raise ValueError(
                "Axiom 1 (CaptureTuningChannelUniqueness) failed: ChannelName must be "
                f"unique across CaptureTuningList; duplicates: {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ZeroTenPowerOnNodeUniqueness.
        NodeName SHALL be unique across ZeroTenPowerOnList.
        """
        names = [z.NodeName for z in self.ZeroTenPowerOnList]
        if len(names) != len(set(names)):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(
                "Axiom 2 (ZeroTenPowerOnNodeUniqueness) failed: NodeName must be "
                f"unique across ZeroTenPowerOnList; duplicates: {duplicates}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: StandbyRefusesDispatch.
        If Standby is true, AcceptsDispatch SHALL be false and
        DispatchRefusalReason SHALL be Standby.
        """
        if self.Standby and (
            self.AcceptsDispatch
            or self.DispatchRefusalReason is not enums.DispatchRefusalReason.Standby
        ):
            raise ValueError(
                "Axiom 3 (StandbyRefusesDispatch) failed: Standby requires "
                "AcceptsDispatch false and DispatchRefusalReason Standby; got "
                f"AcceptsDispatch {self.AcceptsDispatch}, "
                f"DispatchRefusalReason {self.DispatchRefusalReason}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: RefusalReasonPresence.
        DispatchRefusalReason SHALL be present if and only if
        AcceptsDispatch is false.
        """
        if self.AcceptsDispatch == (self.DispatchRefusalReason is not None):
            raise ValueError(
                "Axiom 4 (RefusalReasonPresence) failed: DispatchRefusalReason is "
                "present iff AcceptsDispatch is false; got AcceptsDispatch "
                f"{self.AcceptsDispatch}, DispatchRefusalReason {self.DispatchRefusalReason}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: PostureRelaysPerFamily.
        StandbyPosture fixes EnergizedStandbyRelays for the family named by
        FamilyParams.TypeName: MonitorOnly means an empty list; House0
        NoHeatingOrCooling means exactly hp-failsafe-relay and
        aquastat-ctrl-relay; Nolan NoHeatingOrCooling means an empty list.
        """
        if self.StandbyPosture is StandbyPosture.MonitorOnly:
            expected: List[str] = []
        elif isinstance(self.FamilyParams, House0FamilyParams):
            expected = ["hp-failsafe-relay", "aquastat-ctrl-relay"]
        else:
            expected = []
        if sorted(self.EnergizedStandbyRelays) != sorted(expected):
            raise ValueError(
                "Axiom 5 (PostureRelaysPerFamily) failed: posture "
                f"{self.StandbyPosture} on {self.FamilyParams.TypeName} requires "
                f"EnergizedStandbyRelays {expected}; got {self.EnergizedStandbyRelays}"
            )
        return self
