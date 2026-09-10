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
from typing import List, Optional
from pydantic import ValidationError
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.data_classes.components import (
    GpioRelayComponent,
    I2cRelayComponent,
)
from gwsproto.enums import ActorClass, TurnHpOnOff
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


    def set_command_tree(self, boss_node: ShNode) -> None:
        """
        ```
        boss
        ├── hp-boss
        │     └── hp-scada-ops-relay
        ├── sieg-loop                 (only when the scada runs the loop)
        │     ├── hp-loop-on-off
        │     └── hp-loop-keep-send
        └── every other actuator
        ```
        hp-boss is the heat pump's command node in every layout; the loop
        pair rides only when the ops word says the loop is used.
        Throws exception if boss_node is not in my chain of command
        """

        my_handle_prefix = f"{self.node.handle}."
        if not boss_node.handle.startswith(my_handle_prefix) and boss_node != self.node:
            raise Exception(f"{self.node.handle} cannot set command tree for boss_node {boss_node.handle}!")

        mine = self.my_actuators()
        hp_boss = self.layout.hp_boss
        hp_boss.Handle = f"{boss_node.handle}.{hp_boss.Name}"
        ops_relay = self.layout.hp_scada_ops_relay
        ops_relay.Handle = f"{hp_boss.Handle}.{ops_relay.Name}"
        under_fsm = {ops_relay.Name}
        if self.data.use_sieg_loop:
            sieg_loop = self.layout.node(HSNN.sieg_loop)
            sieg_loop.Handle = f"{boss_node.handle}.{sieg_loop.Name}"
            for name in (House0NodeNames.hp_loop_on_off, House0NodeNames.hp_loop_keep_send):
                node = self.layout.node(name)
                node.Handle = f"{sieg_loop.Handle}.{node.Name}"
                under_fsm.add(node.Name)
        for node in mine:
            if node.Name not in under_fsm:
                node.Handle = f"{boss_node.handle}.{node.Name}"

        self.publish_command_tree()
        self.log(f"Set {boss_node.handle} command tree")

    def publish_command_tree(self) -> None:
        self._send_to(self.ltn, build_command_tree(self.layout))

    def actuator_config(self, node: ShNode):
        """The node's relay control config, or None when the node is not a
        commandable actuator."""
        if node.ActorClass != ActorClass.Relay:
            return None
        component = node.component
        if not isinstance(component, (I2cRelayComponent, GpioRelayComponent)):
            return None
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
        """Command a state-machine transition on a node under me, in the
        node's own event vocabulary: an actuator's config declares its
        events (change.relay.state, change.valve.state,
        change.zone.call.source, ...); hp-boss, the heat pump's command
        node, speaks turn.hp.on.off."""
        if node.ActorClass == ActorClass.HpBoss:
            event_type = TurnHpOnOff.enum_name()
            if event_name not in TurnHpOnOff.values():
                self.log(f"{node.name} ({event_type}) does not accept {event_name}; ignoring")
                return
        else:
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
            event_type = config.EventType
        try:
            event = FsmEvent(
                FromHandle=self.node.handle if from_node is None else from_node.handle,
                ToHandle=node.handle,
                EventType=event_type,
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

