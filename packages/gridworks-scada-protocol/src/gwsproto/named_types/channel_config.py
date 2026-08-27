from pydantic import BaseModel, ConfigDict, PositiveInt, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import Unit
from gwsproto.property_format import (
    SpaceheatName,
)


class ChannelConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/channel.config/000"""

    ChannelName: SpaceheatName
    PollPeriodMs: PositiveInt | None = None
    CapturePeriodS: PositiveInt
    AsyncCapture: bool
    AsyncCaptureDelta:  PositiveInt | None = None
    Exponent: StrictInt
    Unit: Unit
    TypeName: str = "channel.config"
    Version: str = "000"

    model_config = ConfigDict(use_enum_values=True)

    def __hash__(self) -> int:
        return hash(self.ChannelName)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Async Capture Consistency.
        If AsyncCapture is true, AsyncCaptureDelta must be present.
        """
        if self.AsyncCapture and not self.AsyncCaptureDelta:
            raise ValueError(
                "Axiom 1 violated! If AsyncCapture is true, "
                "then AsyncCaptureDelta must exist."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: Capture and Polling Consistency.
        If PollPeriodMs exists, then CapturePeriodMs (CapturePeriodS * 1000)
        must be larger than PollPeriodMs. If CapturePeriodMs is less than
        10 * PollPeriodMs, then CapturePeriodMs must be a multiple of
        PollPeriodMs.
        """
        if self.PollPeriodMs is None:
            return self

        capture_period_ms = self.CapturePeriodS * 1000
        poll_period_ms = self.PollPeriodMs

        if capture_period_ms <= poll_period_ms:
            raise ValueError(
                "Axiom 2 violated! "
                f"CapturePeriodMs {capture_period_ms} must be greater than "
                f"PollPeriodMs {poll_period_ms}."
            )

        if (
            capture_period_ms < 10 * poll_period_ms
            and capture_period_ms % poll_period_ms != 0
        ):
            raise ValueError(
                "Axiom 2 violated! "
                f"CapturePeriodMs {capture_period_ms} must be a multiple of "
                f"PollPeriodMs {poll_period_ms} when CapturePeriodMs is less "
                "than 10 * PollPeriodMs."
            )
        return self
