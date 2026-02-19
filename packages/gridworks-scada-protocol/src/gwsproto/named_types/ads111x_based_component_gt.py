"""Type ads111x.based.component.gt, version 000"""

from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict, field_validator

from gwsproto.named_types.ads_channel_config import (
    AdsChannelConfig,
)
from gwsproto.named_types.component_gt import ComponentGt
from gwsproto.property_format import (
    check_is_near5,
)


class Ads111xBasedComponentGt(ComponentGt):
    OpenVoltageByAds: list[float]
    ConfigList: Sequence[AdsChannelConfig]
    TypeName: Literal["ads111x.based.component.gt"] = "ads111x.based.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("OpenVoltageByAds")
    @classmethod
    def _check_open_voltage_by_ads(cls, v: list[float]) -> list[float]:
        try:
            for elt in v:
                check_is_near5(elt)
        except ValueError as e:
            raise ValueError(
                f"OpenVoltageByAds element failed Near5 format validation: {e}",
            ) from e
        return v

    @field_validator("ConfigList")
    @classmethod
    def check_ads_channel_config_list(
        cls, v: Sequence[AdsChannelConfig]
    ) -> Sequence[AdsChannelConfig]:
        """
            Axiom 1: Terminal Block consistency and Channel Name uniqueness.
            Terminal Block consistency and Channel Name uniqueness. - Each TerminalBlockIdx occurs at
        most once in the ConfigList .Each data channel occurs at most once in the ConfigList
        """
        # Implement Axiom(s)
        return v
