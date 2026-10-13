from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName


class CaptureTuning(SemaType):
    """Sema: https://schemas.electricity.works/types/capture.tuning/000"""

    channel_name: SpaceheatName
    capture_period_s: PositiveInt
    async_capture: bool
    async_capture_delta: PositiveInt | None = None
    poll_period_ms: PositiveInt | None = None
    type_name: Literal["capture.tuning"] = "capture.tuning"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "CaptureTuning":
        """
        Axiom 1: CaptureAndPollingConsistency
        a. If PollPeriodMs is present, CapturePeriodS*1000 SHALL be greater than PollPeriodMs.
        b. If PollPeriodMs is present and CapturePeriodS*1000 is less than 10*PollPeriodMs,
           then CapturePeriodS*1000 SHALL be an integer multiple of PollPeriodMs.
        """
        if self.poll_period_ms is not None:
            capture_ms = self.capture_period_s * 1000
            if not capture_ms > self.poll_period_ms:
                raise ValueError(
                    "Axiom 1 (CaptureAndPollingConsistency) failed: CapturePeriodMs "
                    "must be larger than PollPeriodMs."
                )
            if (
                capture_ms < 10 * self.poll_period_ms
                and capture_ms % self.poll_period_ms != 0
            ):
                raise ValueError(
                    "Axiom 1 (CaptureAndPollingConsistency) failed: CapturePeriodMs "
                    "must be a multiple of PollPeriodMs."
                )
        return self
