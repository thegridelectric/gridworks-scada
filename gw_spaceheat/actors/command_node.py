"""CommandNode — tier B of the sh_node_actor partition: command-tree
mechanics for INTERIOR nodes of the command tree (actors that take commands
from above AND command reports below): Scada's delegates, LocalControl,
LeafAlly, hp-boss, pico-cycler, and the coming circuit FSMs. Leaf actuators
only CHECK handles (relay.py, locally); sensors are outside the tree.

Each interior node is responsible for the tree at-and-under it and publishes
it; today the published payload is the full-tree `new.command.tree` snapshot
(the wire contract is replace-in-entirety). All construction rides
`build_command_tree` — the one funnel, so publication policy changes in one
place.
"""

import time
import uuid
from typing import cast, List, Optional
from pydantic import ValidationError
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.data_classes.components.i2c_multichannel_dt_relay_component import (
    I2cMultichannelDtRelayComponent,
)
from gwsproto.enums import (
    ActorClass
)
from gwsproto.named_types import FsmEvent, NewCommandTree

from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)


from actors.sh_node_actor import ShNodeActor


def build_command_tree(layout: HydronicLayout) -> NewCommandTree:
    """The one construction funnel for the full-tree snapshot every
    interior node publishes after rewriting its part."""
    return NewCommandTree(
        FromGNodeAlias=layout.scada_g_node_alias,
        ShNodes=list(layout.nodes.values()),
        UnixMs=int(time.time() * 1000),
    )


class CommandNode(ShNodeActor):
    """An interior command-tree node: navigates and rewrites the tree at
    and under itself, and publishes the result."""

    def my_actuators(self) -> List[ShNode]:
        """Get all actuator nodes that are descendants of this node in the handle hierarchy"""
        my_handle_prefix = f"{self.node.handle}."
        return [
            node for node in self.layout.actuators
            if node.handle.startswith(my_handle_prefix)
        ]

    @property
    def boss(self) -> ShNode:
        if ".".join(self.node.handle.split(".")[:-1]) == "":
            return self.node

        boss_handle = ".".join(self.node.handle.split(".")[:-1])
        return next(n for n in self.layout.nodes.values() if n.handle == boss_handle)

    def the_boss_of(self, node: ShNode) -> Optional[ShNode]:
        if node.Handle == node.Name:
            return None
        if node.Handle is None:
            return None
        boss_name= node.Handle.split(".")[-2]
        return self.layout.node(boss_name, None)


    def set_hierarchical_fsm_handles(self, boss_node: ShNode) -> None:
        """
        ```
        boss
        ├────────────────────── hp-boss
        └─────sieg-loop         └── relay6 (hp_scada_ops_relay)
                ├─ relay14 (hp_loop_on_off)
                └─ relay15 (hp_loop_keep_send)
        ```
        """
        if not self.data.use_sieg_loop:
            raise Exception("don't call this unless layout uses sieg loop")
        self.log(f"Setting fsm handles under {boss_node.name}")
        hp_boss = self.layout.node(HSNN.hp_boss)
        hp_boss.Handle = f"{boss_node.handle}.{hp_boss.Name}"

        scada_ops_relay = self.layout.node(HSNN.hp_scada_ops_relay)
        scada_ops_relay.Handle = f"{hp_boss.Handle}.{scada_ops_relay.Name}"

        sieg_loop = self.layout.node(HSNN.sieg_loop)
        sieg_loop.Handle = f"{boss_node.handle}.{sieg_loop.Name}"

        sieg_keep_send =  self.layout.node(House0NodeNames.hp_loop_keep_send)
        sieg_keep_send.Handle = f"{sieg_loop.Handle}.{sieg_keep_send.Name}"

        sieg_on_off = self.layout.node(House0NodeNames.hp_loop_on_off)
        sieg_on_off.Handle = f"{sieg_loop.Handle}.{sieg_on_off.Name}"

    def set_command_tree(self, boss_node: ShNode) -> None:
        """
        If FlowManifoldVariant is House0Sieg:
           ```
            boss
            ├─────────────────────────────────────────── hp-boss
            ├───────────────────────────sieg-loop           └── relay6 (hp_scada_ops_relay)
            ├                             ├─ relay14 (hp_loop_on_off)
            ├── relay1 (vdc)              └─ relay15 (hp_loop_keep_send)
            ├── relay2 (tstat_common)
            └── all other relays and 0-10s
        ```
        If FlowManifoldVariant is House0, all actuators report directly to boss
        Throws exception if boss_node is not in my chain of command
        """

        my_handle_prefix = f"{self.node.handle}."
        if not boss_node.handle.startswith(my_handle_prefix) and boss_node != self.node:
            raise Exception(f"{self.node.handle} cannot set command tree for boss_node {boss_node.handle}!")

        if self.data.use_sieg_loop:
            self.set_hierarchical_fsm_handles(boss_node)
            for node in self.my_actuators():
                if node.Name not in [HSNN.hp_scada_ops_relay, House0NodeNames.hp_loop_keep_send, House0NodeNames.hp_loop_on_off]:
                    node.Handle =  f"{boss_node.handle}.{node.Name}"
        else:
            for node in self.my_actuators():
                node.Handle =  f"{boss_node.handle}.{node.Name}"

        self.publish_command_tree()
        self.log(f"Set {boss_node.handle} command tree")

    def publish_command_tree(self) -> None:
        self._send_to(self.ltn, build_command_tree(self.layout))

    def actuator_config(self, node: ShNode):
        """The node's relay control config, or None when the node is not a
        commandable actuator."""
        if node.ActorClass != ActorClass.Relay:
            return None
        component = cast(I2cMultichannelDtRelayComponent, node.component)
        return next(
            (x for x in component.gt.ConfigList if x.ActorName == node.name),
            None,
        )

    def send_state_command(
        self,
        node: ShNode,
        event_name: str,
        from_node: Optional[ShNode] = None,
    ) -> None:
        """Command a state-machine transition on an actuator node, in the
        node's own event vocabulary (change.relay.state,
        change.valve.state, change.zone.call.source, ...). The event name
        must be one the node's config declares."""
        config = self.actuator_config(node)
        if config is None:
            self.log(f"{node.name} is not a commandable actuator; ignoring {event_name}")
            return
        if event_name not in (config.EnergizingEvent, config.DeEnergizingEvent):
            self.log(
                f"{node.name} ({config.EventType}) does not accept "
                f"{event_name}; ignoring"
            )
            return
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=node.handle,
                EventType=config.EventType,
                EventName=event_name,
                SendTimeUnixMs=int(time.time() * 1000),
                TriggerId=str(uuid.uuid4()),
            )
            self._send_to(node, event, from_node)
            self.log(f"{event_name} to {node.name}")
        except ValidationError as e:
            self.log(
                f"Tried to command {event_name} on {node.name} but didn't "
                f"have the rights: {e}"
            )

    def energize(self, relay: ShNode, from_node: Optional[ShNode] = None):
        """Pin-level convenience: the node's energizing event, whatever it
        means in that actuator's vocabulary."""
        config = self.actuator_config(relay)
        if config is None:
            self.log(f"Unrecognized relay {relay.name}. Not energizing")
            return
        self.send_state_command(relay, config.EnergizingEvent, from_node)

    def de_energize(self, relay: ShNode, from_node: Optional[ShNode] = None):
        """Pin-level convenience: the node's de-energizing event, whatever
        it means in that actuator's vocabulary."""
        config = self.actuator_config(relay)
        if config is None:
            self.log(f"Unrecognized relay {relay.name}. Not de-energizing")
            return
        self.send_state_command(relay, config.DeEnergizingEvent, from_node)

