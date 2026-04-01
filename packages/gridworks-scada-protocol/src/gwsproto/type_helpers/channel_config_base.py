from typing import TypeVar

from pydantic import BaseModel, ConfigDict, PositiveInt, StrictInt

from gwsproto.enums import Unit
from gwsproto.property_format import SpaceheatName


class ChannelConfigBase(BaseModel):
    ChannelName: SpaceheatName
    PollPeriodMs: PositiveInt | None = None
    CapturePeriodS: PositiveInt
    AsyncCapture: bool
    AsyncCaptureDelta: PositiveInt | None = None
    Exponent: StrictInt
    Unit: Unit

    model_config = ConfigDict(use_enum_values=True)

    def __hash__(self) -> int:
        return hash(self.ChannelName)


TChannelConfigBase = TypeVar("TChannelConfigBase", bound=ChannelConfigBase)


def check_async_capture_consistency(
    config: TChannelConfigBase,
) -> TChannelConfigBase:
    if config.AsyncCapture and not config.AsyncCaptureDelta:
        raise ValueError(
            "Axiom 1 violated! If AsyncCapture is true, "
            "then AsyncCaptureDelta must exist."
        )
    return config


def check_channel_config_axiom_1(
    config: TChannelConfigBase, axiom_number: int = 1
) -> TChannelConfigBase:
    if config.PollPeriodMs is None:
        return config

    capture_period_ms = config.CapturePeriodS * 1000
    poll_period_ms = config.PollPeriodMs

    if capture_period_ms <= poll_period_ms:
        raise ValueError(
            f"Axiom {axiom_number} violated! "
            f"CapturePeriodMs {capture_period_ms} must be greater than "
            f"PollPeriodMs {poll_period_ms}."
        )

    if (
        capture_period_ms < 10 * poll_period_ms
        and capture_period_ms % poll_period_ms != 0
    ):
        raise ValueError(
            f"Axiom {axiom_number} violated! "
            f"CapturePeriodMs {capture_period_ms} must be a multiple of "
            f"PollPeriodMs {poll_period_ms} when CapturePeriodMs is less "
            "than 10 * PollPeriodMs."
        )
    return config
