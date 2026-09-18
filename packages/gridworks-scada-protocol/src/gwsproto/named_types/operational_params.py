from typing import Annotated, List, Literal, Union

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import ActuationAuthority, ServiceMode
from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.named_types.cop_curve import CopCurve
from gwsproto.named_types.heating_curve import HeatingCurve
from gwsproto.named_types.house0_family_params import House0FamilyParams
from gwsproto.named_types.nolan_family_params import NolanFamilyParams
from gwsproto.named_types.tou_tariff import TouTariff
from gwsproto.named_types.zero_ten_power_on import ZeroTenPowerOn
from gwsproto.property_format import LeftRightDotStr
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
    ActuationAuthority: ActuationAuthority
    ServiceMode: ServiceMode
    CopCurve: CopCurve
    HeatingCurve: HeatingCurve
    HpTurnOnMinutes: PositiveInt
    HpMaxKwEl: PositiveFloat
    LoadOverestimationPercent: NonNegativeInt
    OilBoilerBackup: bool
    HorizonHours: PositiveInt
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
