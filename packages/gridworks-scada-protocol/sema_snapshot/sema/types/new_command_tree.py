from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.types.spaceheat_node_gt import SpaceheatNodeGt


class NewCommandTree(SemaType):
    """Sema: https://schemas.electricity.works/types/new.command.tree/003"""

    from_g_node_alias: LeftRightDot
    sh_nodes: list[SpaceheatNodeGt]
    unix_ms: UTCMilliseconds
    type_name: Literal["new.command.tree"] = "new.command.tree"
    version: Literal["003"] = "003"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "NewCommandTree":
        """
        Axiom 1: PrefixClosedHandles
        Let the effective handle of an ShNode be its Handle if present, otherwise
        its Name. The set of effective handles SHALL be prefix-closed: for every ShNode
        in ShNodes, each dot-separated prefix of its effective handle SHALL also be the
        effective handle of some ShNode in ShNodes.
        """
        effective = {
            node.handle if node.handle is not None else node.name
            for node in self.sh_nodes
        }
        for value in effective:
            segments = value.split(".")
            for n in range(1, len(segments)):
                prefix = ".".join(segments[:n])
                if prefix not in effective:
                    raise ValueError(
                        f"Axiom 1 failed: effective handle {value!r} has "
                        f"prefix {prefix!r} that is not the effective handle "
                        "of any ShNode."
                    )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "NewCommandTree":
        """
        Axiom 2: ActuatorLeaves
        Let the effective handle of an ShNode be its Handle if present, otherwise
        its Name. A leaf is an ShNode whose effective handle contains a dot and is
        the parent prefix of no other effective handle. An actuator is an ShNode
        whose ActorClass is "Relay", "ZeroTenOutputer" or "HpTwin". A command node
        is an ShNode whose ActorClass is "LocalControl", "LeafAlly", "FiveVBoss",
        "PicoCycler", "HpBoss" or "SiegLoop", or whose ActorClass is "NoActor" and whose
        effective handle's parent prefix is the effective handle of an ShNode with
        ActorClass "LocalControl".
        a. Every actuator SHALL have a dotted effective handle and SHALL be a leaf.
        b. Every leaf SHALL be an actuator or a command node.
        """
        actuator_classes = {"Relay", "ZeroTenOutputer", "HpTwin"}
        command_classes = {
            "LocalControl",
            "LeafAlly",
            "FiveVBoss",
            "PicoCycler",
            "HpBoss",
            "SiegLoop",
        }
        by_handle = {
            (node.handle if node.handle is not None else node.name): node
            for node in self.sh_nodes
        }
        handles = set(by_handle)
        lc_handles = {
            h for h, n in by_handle.items() if str(n.actor_class) == "LocalControl"
        }

        def is_leaf(handle: str) -> bool:
            return "." in handle and not any(
                other.startswith(handle + ".") for other in handles
            )

        for handle, node in by_handle.items():
            actor_class = str(node.actor_class)
            if actor_class in actuator_classes and not is_leaf(handle):
                raise ValueError(
                    f"Axiom 2 (ActuatorLeaves) failed: actuator {node.name!r} with "
                    f"handle {handle!r} is not a dotted-handle leaf."
                )
            if is_leaf(handle):
                parent = handle.rsplit(".", 1)[0]
                is_command = actor_class in command_classes or (
                    actor_class == "NoActor" and parent in lc_handles
                )
                if actor_class not in actuator_classes and not is_command:
                    raise ValueError(
                        f"Axiom 2 (ActuatorLeaves) failed: leaf {node.name!r} with "
                        f"handle {handle!r} (ActorClass {actor_class}) is neither an "
                        "actuator nor a command node."
                    )
        return self
