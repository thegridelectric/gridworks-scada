from typing import List, Literal

from pydantic import BaseModel, NonNegativeInt, PositiveFloat, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import ActuationAuthority, SeasonalStorageMode, ServiceMode
from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.named_types.cop_curve import CopCurve
from gwsproto.named_types.heating_curve import HeatingCurve
from gwsproto.named_types.tou_window import TouWindow
from gwsproto.property_format import LeftRightDotStr


class NolanOperationalParams(BaseModel):
    """Sema: https://schemas.electricity.works/types/gw.nolan.operational.params/000

    ⏳ TEMPORARY: the House0 store/optimization knobs (SeasonalStorageMode,
    HpTurnOnMinutes, ShortCycleBuffer, LoadOverestimationPercent,
    OilBoilerBackup, HorizonHours) are carried here so a Nolan home can drive
    the House0-shaped surfaces that still run for every family — the LeafAlly
    strategy selection and layout.lite, which requires them. Nolan has no
    thermal store to season, so these are not Nolan concepts; they come back
    out as the functional code is moved off them.
    """

    ScadaAlias: LeftRightDotStr
    CaptureTuningList: List[CaptureTuning]
    ActuationAuthority: ActuationAuthority
    ServiceMode: ServiceMode
    SeasonalStorageMode: SeasonalStorageMode
    CopCurve: CopCurve
    HeatingCurve: HeatingCurve
    HpTurnOnMinutes: PositiveInt
    HpMaxKwEl: PositiveFloat
    ShortCycleBuffer: bool
    LoadOverestimationPercent: NonNegativeInt
    OilBoilerBackup: bool
    HorizonHours: PositiveInt
    OnPeakWindows: List[TouWindow]
    TypeName: Literal["gw.nolan.operational.params"] = "gw.nolan.operational.params"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: CaptureTuningChannelUniqueness.
        ChannelName SHALL be unique across CaptureTuningList.
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
        Axiom 2: PerDayWindowNonOverlap.
        For each day of the week, the windows in OnPeakWindows whose Days
        include that day SHALL NOT overlap one another.
        """
        days = {day for w in self.OnPeakWindows for day in w.Days}
        for day in days:
            todays = sorted(
                (w for w in self.OnPeakWindows if day in w.Days),
                key=lambda w: w.Start,
            )
            for earlier, later in zip(todays, todays[1:]):
                if later.Start < earlier.End:
                    raise ValueError(
                        "Axiom 2 (PerDayWindowNonOverlap) failed: on "
                        f"{day} window {later.Start}-{later.End} overlaps "
                        f"{earlier.Start}-{earlier.End}."
                    )
        return self
