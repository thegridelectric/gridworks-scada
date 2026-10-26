from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import ActorClass
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.types.command_interface import CommandInterface
from sema_snapshot.sema.types.data_channel_gt import DataChannelGt
from sema_snapshot.sema.types.spaceheat_node_gt import SpaceheatNodeGt


class ScadaControlCapabilities(SemaType):
    """Sema: https://schemas.electricity.works/types/scada.control.capabilities/002"""

    from_g_node_alias: LeftRightDot
    message_created_ms: UTCMilliseconds
    relay_nodes: list[SpaceheatNodeGt]
    dac_nodes: list[SpaceheatNodeGt]
    command_nodes: list[SpaceheatNodeGt]
    control_channels: list[DataChannelGt]
    command_interfaces: list[CommandInterface]
    type_name: Literal["scada.control.capabilities"] = "scada.control.capabilities"
    version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ScadaControlCapabilities":
        """
        Axiom 1: ActorClassConsistency
        a. All nodes in RelayNodes SHALL have ActorClass equal to Relay.
        b. All nodes in DacNodes SHALL have ActorClass equal to ZeroTenOutputer.
        c. No node in CommandNodes SHALL have ActorClass equal to Relay or ZeroTenOutputer.
        """
        actuator_classes = {
            ActorClass.Relay,
            ActorClass.ZeroTenOutputer,
        }
        for node in self.relay_nodes:
            if node.actor_class != ActorClass.Relay:
                raise ValueError(
                    "Axiom 1 failed: every relay_nodes actor_class must be Relay."
                )
        for node in self.dac_nodes:
            if node.actor_class != ActorClass.ZeroTenOutputer:
                raise ValueError(
                    "Axiom 1 failed: every dac_nodes actor_class must be ZeroTenOutputer."
                )
        for node in self.command_nodes:
            if node.actor_class in actuator_classes:
                raise ValueError(
                    "Axiom 1 failed: command_nodes actor_class must not be Relay or "
                    "ZeroTenOutputer."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "ScadaControlCapabilities":
        """
        Axiom 2: HandleTerminalMatchesName
        For every node in RelayNodes, DacNodes and CommandNodes, Handle SHALL be present
        and its final dot-separated token SHALL equal Name.
        """
        for node in [*self.relay_nodes, *self.dac_nodes, *self.command_nodes]:
            if node.handle is None:
                raise ValueError(
                    "Axiom 2 failed: every control node must have a handle."
                )
            if str(node.handle).split(".")[-1] != node.name:
                raise ValueError(
                    "Axiom 2 failed: every control node handle terminal token must equal name."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "ScadaControlCapabilities":
        """
        Axiom 3: AboutNodesAreControlNodes
        The set of ControlChannels.AboutNodeName values SHALL equal the set of
        RelayNodes.Name and DacNodes.Name values.
        """
        control_node_names = {
            node.name for node in [*self.relay_nodes, *self.dac_nodes]
        }
        channel_about_node_names = {
            channel.about_node_name for channel in self.control_channels
        }
        if channel_about_node_names != control_node_names:
            raise ValueError(
                "Axiom 3 failed: control_channels about_node_name values must equal "
                "relay_nodes and dac_nodes names."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "ScadaControlCapabilities":
        """
        Axiom 4: CommandInterfacesCoverTheTree
        a. The set of CommandInterfaces.ActorName values SHALL equal the set of Name
        values of the nodes in RelayNodes and CommandNodes whose Handle does not extend
        the Handle of any CommandNodes entry (a Handle extends another when it equals
        that Handle followed by a dot and further tokens).
        b. No two CommandInterfaces entries SHALL share both an ActorName and an
        EventType; a node with more than one command vocabulary carries one
        entry per vocabulary.
        """
        owner_prefixes = [
            f"{node.handle}." for node in self.command_nodes if node.handle is not None
        ]
        directly_commanded = {
            node.name
            for node in [*self.relay_nodes, *self.command_nodes]
            if node.handle is not None
            and not any(str(node.handle).startswith(p) for p in owner_prefixes)
        }
        interface_names = [
            interface.actor_name for interface in self.command_interfaces
        ]
        if set(interface_names) != directly_commanded:
            raise ValueError(
                "Axiom 4 failed: command_interfaces actor_name values must equal the "
                "names of the relay and command nodes the root commands directly."
            )
        pairs = [
            (interface.actor_name, interface.event_type)
            for interface in self.command_interfaces
        ]
        if len(pairs) != len(set(pairs)):
            raise ValueError(
                "Axiom 4 failed: no two command_interfaces entries may share both "
                "actor_name and event_type."
            )
        return self
