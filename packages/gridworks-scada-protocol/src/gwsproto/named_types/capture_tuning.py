from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class CaptureTuning(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/capture.tuning/000"""

    ChannelName: SpaceheatName
    CapturePeriodS: PositiveInt
    AsyncCapture: bool
    AsyncCaptureDelta: Optional[PositiveInt] = None
    PollPeriodMs: Optional[PositiveInt] = None
    TypeName: Literal["capture.tuning"] = "capture.tuning"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    def __hash__(self) -> int:
        return hash(self.ChannelName)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: CaptureAndPollingConsistency.
        a. If PollPeriodMs is present, CapturePeriodS*1000 SHALL be greater
        than PollPeriodMs.
        b. If PollPeriodMs is present and CapturePeriodS*1000 is less than
        10*PollPeriodMs, then CapturePeriodS*1000 SHALL be an integer
        multiple of PollPeriodMs.
        """
        if self.PollPeriodMs is None:
            return self
        capture_period_ms = self.CapturePeriodS * 1000
        poll_period_ms = self.PollPeriodMs
        if capture_period_ms <= poll_period_ms:
            raise ValueError(
                "Axiom 1 (CaptureAndPollingConsistency) failed: "
                f"CapturePeriodMs {capture_period_ms} must be greater than "
                f"PollPeriodMs {poll_period_ms}."
            )
        if (
            capture_period_ms < 10 * poll_period_ms
            and capture_period_ms % poll_period_ms != 0
        ):
            raise ValueError(
                "Axiom 1 (CaptureAndPollingConsistency) failed: "
                f"CapturePeriodMs {capture_period_ms} must be a multiple of "
                f"PollPeriodMs {poll_period_ms} when CapturePeriodMs is less "
                "than 10 * PollPeriodMs."
            )
        return self
