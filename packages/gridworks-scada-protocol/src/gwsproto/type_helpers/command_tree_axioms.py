"""The command-tree shape axioms shared by new.command.tree and the layout
words: a layout's authored handles are the initial command tree, so both
carry PrefixClosedHandles and ActuatorLeaves with identical wording. One
implementation here; each type's check_axiom_<n> supplies its own label."""

from typing import Iterable

from gwsproto.enums import ActorClass
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.names.core.node_names import CoreNodeNames

ACTUATOR_CLASSES = {ActorClass.Relay, ActorClass.ZeroTenOutputer, ActorClass.HpTwin}
LOCAL_CONTROL_STATE_NODES = {
    CoreNodeNames.local_control_normal,
    CoreNodeNames.local_control_backup,
    CoreNodeNames.local_control_scada_blind,
}
COMMAND_CLASSES = {
    ActorClass.LocalControl,
    ActorClass.LeafAlly,
    ActorClass.FiveVBoss,
    ActorClass.PicoCycler,
    ActorClass.HpBoss,
    ActorClass.SiegLoop,
}


def effective_handle(node: SpaceheatNodeGt) -> str:
    return node.Handle if node.Handle is not None else node.Name


def check_prefix_closed_handles(nodes: Iterable[SpaceheatNodeGt], axiom: str) -> None:
    """Every dot-separated prefix of an effective handle is itself an
    effective handle of some node."""
    effective = {effective_handle(n) for n in nodes}
    for handle in sorted(effective):
        segments = handle.split(".")
        for n in range(1, len(segments)):
            prefix = ".".join(segments[:n])
            if prefix not in effective:
                raise ValueError(
                    f"{axiom} failed: effective handle {handle!r} has prefix "
                    f"{prefix!r} that is not the effective handle of any ShNode"
                )


def check_actuator_leaves(nodes: Iterable[SpaceheatNodeGt], axiom: str) -> None:
    """a. every actuator has a dotted effective handle and is a leaf;
    b. every dotted-handle leaf is an actuator or a command node (a
    command class, or a NoActor directly under the LocalControl node);
    c. the NoActor nodes directly under the LocalControl node are named
    n, backup or scada-blind."""
    by_handle = {effective_handle(n): n for n in nodes}
    handles = set(by_handle)
    lc_handles = {h for h, n in by_handle.items() if n.ActorClass == ActorClass.LocalControl}

    def is_leaf(handle: str) -> bool:
        return "." in handle and not any(o.startswith(handle + ".") for o in handles)

    for handle, node in by_handle.items():
        if node.ActorClass in ACTUATOR_CLASSES and not is_leaf(handle):
            raise ValueError(
                f"{axiom} failed: actuator {node.Name!r} with handle {handle!r} "
                "is not a dotted-handle leaf."
            )
        if is_leaf(handle):
            parent = handle.rsplit(".", 1)[0]
            is_command = node.ActorClass in COMMAND_CLASSES or (
                node.ActorClass == ActorClass.NoActor and parent in lc_handles
            )
            if node.ActorClass not in ACTUATOR_CLASSES and not is_command:
                raise ValueError(
                    f"{axiom} failed: leaf {node.Name!r} with handle {handle!r} "
                    f"(ActorClass {node.ActorClass}) is neither an actuator nor a "
                    "command node."
                )
        if (
            node.ActorClass == ActorClass.NoActor
            and "." in handle
            and handle.rsplit(".", 1)[0] in lc_handles
            and node.Name not in LOCAL_CONTROL_STATE_NODES
        ):
            raise ValueError(
                f"{axiom} failed: {node.Name!r} with handle {handle!r} is a NoActor "
                "node under local control other than n, backup or scada-blind."
            )
