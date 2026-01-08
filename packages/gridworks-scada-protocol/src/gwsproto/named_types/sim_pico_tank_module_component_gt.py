from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import TempCalcMethod
from gwsproto.named_types.component_gt import ComponentGt



class SimPicoTankModuleComponentGt(ComponentGt):
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
    SimulatesTypeName: Literal["pico.tank.module.component.gt"] = "pico.tank.module.component.gt"
    SimulatesVersion: Literal["011"] = "011"
    TypeName: Literal["sim.pico.tank.module.component.gt"] = "sim.pico.tank.module.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PicoHwUid exists  XOR (both PicoAHwUid and PicoBHwUid exist)
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
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: PicoKOhms exists iff TempCalcMethod is TempCalcMethod.SimpleBetaForPico
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

    def check_axiom_3(self) -> None:
        """
        Axiom 3:
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

    