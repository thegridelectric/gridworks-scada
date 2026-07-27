from collections.abc import Sequence
from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt, field_validator, model_validator
from typing_extensions import Self

from gwsproto.enums import TempCalcMethod
from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.type_helpers.component_base import DeviceComponentBase


class PicoTankModuleComponentGt(DeviceComponentBase):
    Enabled: bool
    PicoHwUid: Optional[str] = None
    PicoAHwUid: Optional[str] = None
    PicoBHwUid: Optional[str] = None
    TempCalcMethod: TempCalcMethod
    ThermistorBeta: PositiveInt
    SendMicroVolts: bool
    Samples: PositiveInt
    NumSampleAverages: PositiveInt
    PicoKOhms: PositiveInt | None = None
    SerialNumber: str = "NA"
    AsyncCaptureDeltaMicroVolts: int
    SensorOrder: list[int] | None = None
    TypeName: Literal["pico.tank.module.component.gt"] = "pico.tank.module.component.gt"
    Version: Literal["012"] = "012"

    model_config = ConfigDict(extra="allow")

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: Sequence[CaptureTuning]) -> Sequence[CaptureTuning]:
        """Axiom 1: Channel Name uniqueness. Data Channel names are unique in the ConfigList."""
        channel_names = [config.ChannelName for config in v]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                f"Axiom 1 violated! Channel names must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: PicoHwUid exists  XOR (both PicoAHwUid and PicoBHwUid exist)
        """
        if self.PicoHwUid is not None:
            if self.PicoAHwUid or self.PicoBHwUid:
                raise ValueError(
                    "Can't have both PicoHwUid and any of (PicoAHwUid, PicoBHwUid"
                )
        elif not (self.PicoAHwUid and self.PicoBHwUid):
            raise ValueError(
                "If PicoHwUid is not set, PicoAHwUid and PicoBHwUid must both be set!"
            )

        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: PicoKOhms exists iff TempCalcMethod is TempCalcMethod.SimpleBetaForPico
        # note this is a known incorrect method, but there are a few in the field
        # that do this.
        """
        is_simple_beta = self.TempCalcMethod == TempCalcMethod.SimpleBetaForPico
        has_kohms = self.PicoKOhms is not None

        if is_simple_beta != has_kohms:
            raise ValueError(
                "PicoKOhms must be provided if and only if TempCalcMethod is SimpleBetaForPico"
            )

        return self

    def check_axiom_4(self) -> None:
        """
        Axiom 4:
        If SensorOrder is provided, it must be a permutation of [1, 2, 3].
        """
        if self.SensorOrder is None:
            return

        expected = [1, 2, 3]
        order = self.SensorOrder

        # Must be length 3
        if len(order) != 3:
            raise ValueError(f"SensorOrder must be length 3 if provided; got {order}")

        # Must contain exactly the integers 1, 2, 3 with no duplicates
        if sorted(order) != expected:
            raise ValueError(
                f"SensorOrder must be a permutation of {expected}; got {order}"
            )
