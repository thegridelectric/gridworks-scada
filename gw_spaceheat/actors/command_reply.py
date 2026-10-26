"""What a bossable node owes its boss. Two replies: DispatchAck once the
command is taken (before actuation, which the node's state report then
confirms) and DispatchNack with the reason on every refusal. Built here so
relays, 0-10V outputers and the interior command nodes (pico-cycler,
hp-boss, five-v-boss, sieg-loop) answer in one shape; the reply goes back
to the commanding node, which for admin means the admin link.

And the written record: the node's fsm.full.report under the command's
TriggerId. It goes to the commander when the commander is an interior
command node, which folds it into its own report under the same id;
otherwise to the scada, the journal. So one report per TriggerId reaches
the scada, and none goes to the admin panel, which follows state rows."""

import time

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass, ScadaCmdRefusalReason
from gwsproto.named_types import DispatchAck, DispatchNack
from gwsproto.property_format import HandleName, UUID4Str

# The interior command nodes: they take commands from above, command
# actuators below, and fold their subordinates' full reports into their own.
COMMAND_NODE_CLASSES = {ActorClass.FiveVBoss, ActorClass.PicoCycler, ActorClass.HpBoss, ActorClass.SiegLoop}


def report_destination(commander: ShNode, primary_scada: ShNode) -> ShNode:
    """Where a full report under the commander's TriggerId goes: to a
    commander that folds, else to the scada."""
    return commander if commander.ActorClass in COMMAND_NODE_CLASSES else primary_scada


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
    reason: ScadaCmdRefusalReason,
) -> DispatchNack:
    return DispatchNack(
        FromHandle=my_handle,
        ToHandle=commander_handle,
        TriggerId=trigger_id,
        Reason=reason,
        UnixTimeMs=int(time.time() * 1000),
    )
