from typing import Literal
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.ads_channel_config import AdsChannelConfig


class Ads111xBasedComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/ads111x.based.component.gt/000"""

    component_id: UUID4Str
    device_type: PascalCase
    config_list: list[AdsChannelConfig]
    open_voltage_by_ads: list[StrictFloat]
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["ads111x.based.component.gt"] = "ads111x.based.component.gt"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "Ads111xBasedComponentGt":
        """
        Axiom 1: ChannelNameUniqueness
        Channel names SHALL be unique across the ConfigList.
        """
        channel_names = [config.channel_name for config in self.config_list]
        if len(channel_names) != len(set(channel_names)):
            raise ValueError(
                "Axiom 1 (ChannelNameUniqueness) failed: channel names must be "
                "unique across the ConfigList."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "Ads111xBasedComponentGt":
        """
        Axiom 2: OpenVoltageByAdsRange
        Every element of OpenVoltageByAds SHALL be between 4.5 and 5.5 inclusive
        (the "near 5V" Raspberry-Pi-supply open-circuit range).
        """
        for v in self.open_voltage_by_ads:
            if not 4.5 <= v <= 5.5:
                raise ValueError(
                    f"Axiom 2 (OpenVoltageByAdsRange): OpenVoltageByAds element {v} "
                    "is not between 4.5 and 5.5."
                )
        return self
