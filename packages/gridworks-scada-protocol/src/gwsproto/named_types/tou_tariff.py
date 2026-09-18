from typing import List, Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.named_types.tou_window import TouWindow
from gwsproto.property_format import IanaTimezoneStr, LeftRightDotStr
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class TouTariff(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.tou.tariff/000"""

    Alias: LeftRightDotStr
    DisplayName: str
    TimezoneStr: IanaTimezoneStr
    OnPeakWindows: List[TouWindow]
    TypeName: Literal["gw.tou.tariff"] = "gw.tou.tariff"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PerDayWindowNonOverlap.
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
                        "Axiom 1 (PerDayWindowNonOverlap) failed: on "
                        f"{day} window {later.Start}-{later.End} overlaps "
                        f"{earlier.Start}-{earlier.End}."
                    )
        return self
