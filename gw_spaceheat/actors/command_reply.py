"""The two replies a command node owes its commander: DispatchAck once the
command is taken (before actuation, which the node's state report then
confirms) and DispatchNack with the reason on every refusal. Built here so
the four command nodes (relay, 0-10V outputer, pico-cycler, hp-boss) answer
in one shape; the reply goes back to the commanding node, which for admin
means the admin link."""

import time

from gwsproto.enums import GwScadaCmdRefusalReason
from gwsproto.named_types import DispatchAck, DispatchNack
from gwsproto.property_format import HandleName, UUID4Str


def ack(my_handle: HandleName, commander_handle: HandleName, trigger_id: UUID4Str) -> DispatchAck:
    return DispatchAck(
        FromHandle=my_handle,
        ToHandle=commander_handle,
        TriggerId=trigger_id,
        UnixTimeMs=int(time.time() * 1000),
    )


def nack(
    my_handle: HandleName,
    commander_handle: HandleName,
    trigger_id: UUID4Str,
    reason: GwScadaCmdRefusalReason,
) -> DispatchNack:
    return DispatchNack(
        FromHandle=my_handle,
        ToHandle=commander_handle,
        TriggerId=trigger_id,
        Reason=reason,
        UnixTimeMs=int(time.time() * 1000),
    )
