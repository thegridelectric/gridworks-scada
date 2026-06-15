"""Type ads111x.based.component.gt, version 000"""

from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict, field_validator, model_validator
from typing_extensions import Self

from gwsproto.named_types.ads_channel_config import (
    AdsChannelConfig,
)
from gwsproto.named_types.component_gt import ComponentGt


class Ads111xBasedComponentGt(ComponentGt):
    OpenVoltageByAds: list[float]
    ConfigList: Sequence[AdsChannelConfig]
    TypeName: Literal["ads111x.based.component.gt"] = "ads111x.based.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: OpenVoltageByAdsRange (mirrors sema ads111x.based.component.gt/000).
        Every element of OpenVoltageByAds SHALL be between 4.5 and 5.5 inclusive
        (the "near 5V" Raspberry-Pi-supply open-circuit range). Replaces the old
        Near5 property format with a sema axiom.
        """
        for v in self.OpenVoltageByAds:
            if not 4.5 <= v <= 5.5:
                raise ValueError(
                    f"Axiom 1 (OpenVoltageByAdsRange): OpenVoltageByAds element {v} "
                    "is not between 4.5 and 5.5."
                )
        return self

    @field_validator("ConfigList")
    @classmethod
    def check_config_list(
        cls, v: Sequence[AdsChannelConfig]
    ) -> Sequence[AdsChannelConfig]:
        """
        gwsproto-local ConfigList check (not a sema axiom): TerminalBlockIdx and
        ChannelName SHALL each be unique across the ConfigList. (TODO: implement.)
        """
        return v
