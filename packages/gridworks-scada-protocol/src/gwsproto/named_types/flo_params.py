from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import SeasonalStorageMode
from gwsproto.named_types.flo_optimal_path import FloOptimalPath
from gwsproto.named_types.flo_tuning_alice import FloTuningAlice
from gwsproto.named_types.flo_tuning_bruce import FloTuningBruce
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds, UTCSeconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.params/001"""

    GNodeAlias: LeftRightDotStr
    CreatedMs: UTCMilliseconds
    StartUnixS: UTCSeconds
    StepDurationMinutes: List[PositiveInt]
    LmpUsdMwhList: List[float]
    DistUsdMwhList: List[float]
    OatFList: List[float]
    LoadKwhList: List[float]
    RswtFList: List[float]
    WeatherForecastId: UUID4Str
    SeasonalStorageMode: SeasonalStorageMode
    TanksModeled: PositiveInt
    GallonsPerTank: PositiveInt
    TempSensorsPerTank: PositiveInt
    MaxTankTempF: float
    InitialTopTempF: float
    InitialMiddleTempF: float
    InitialBottomTempF: float
    InitialThermocline1: PositiveInt
    InitialThermocline2: PositiveInt
    HpCurrentlyOn: bool
    HpMaxKwEl: float
    HpTurnOnMinutes: PositiveInt
    CopIntercept: float
    CopOatCoeff: float
    CopLwtCoeff: float
    CopMin: float
    CopMinOatF: float
    PriceMaxUsdMwh: float
    PriceMinUsdMwh: float
    PreviousOptimalPath: Optional[FloOptimalPath] = None
    PreviousEstimateElecUsdMwhNow: Optional[float] = None
    Tuning: Annotated[
        Union[FloTuningAlice, FloTuningBruce],
        Field(discriminator="TypeName"),
    ]
    TypeName: Literal["flo.params"] = "flo.params"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: StepListLengths.
        StepDurationMinutes, LmpUsdMwhList, DistUsdMwhList, OatFList,
        LoadKwhList and RswtFList SHALL be non-empty and of the same length.
        """
        lengths = {
            "StepDurationMinutes": len(self.StepDurationMinutes),
            "LmpUsdMwhList": len(self.LmpUsdMwhList),
            "DistUsdMwhList": len(self.DistUsdMwhList),
            "OatFList": len(self.OatFList),
            "LoadKwhList": len(self.LoadKwhList),
            "RswtFList": len(self.RswtFList),
        }
        if len(set(lengths.values())) != 1 or lengths["StepDurationMinutes"] == 0:
            raise ValueError(
                "Axiom 1 (StepListLengths) failed: the per-step lists must be "
                f"non-empty and of one length; got {lengths!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ThermoclinesWithinTheStore.
        InitialThermocline1 SHALL be at most InitialThermocline2, and
        InitialThermocline2 SHALL be at most TempSensorsPerTank times
        TanksModeled.
        """
        top = self.TempSensorsPerTank * self.TanksModeled
        if not (self.InitialThermocline1 <= self.InitialThermocline2 <= top):
            raise ValueError(
                "Axiom 2 (ThermoclinesWithinTheStore) failed: need "
                f"InitialThermocline1 ({self.InitialThermocline1}) <= "
                f"InitialThermocline2 ({self.InitialThermocline2}) <= "
                f"TempSensorsPerTank * TanksModeled ({top})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: BufferIsOneTank.
        If SeasonalStorageMode is BufferOnly, TanksModeled SHALL be 1.
        """
        if self.SeasonalStorageMode == SeasonalStorageMode.BufferOnly and self.TanksModeled != 1:
            raise ValueError(
                "Axiom 3 (BufferIsOneTank) failed: BufferOnly models one tank; "
                f"got TanksModeled {self.TanksModeled}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: PriceBounds.
        PriceMinUsdMwh SHALL be less than PriceMaxUsdMwh.
        """
        if not self.PriceMinUsdMwh < self.PriceMaxUsdMwh:
            raise ValueError(
                f"Axiom 4 (PriceBounds) failed: PriceMinUsdMwh ({self.PriceMinUsdMwh}) "
                f"must be less than PriceMaxUsdMwh ({self.PriceMaxUsdMwh})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: PreviousRunTogether.
        PreviousOptimalPath and PreviousEstimateElecUsdMwhNow SHALL be
        both present or both absent.
        """
        if (self.PreviousOptimalPath is None) != (self.PreviousEstimateElecUsdMwhNow is None):
            raise ValueError(
                "Axiom 5 (PreviousRunTogether) failed: PreviousOptimalPath and "
                "PreviousEstimateElecUsdMwhNow must be both present or both absent."
            )
        return self
