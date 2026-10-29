from typing import List, Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import ActorClass
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.command_interface import CommandInterface
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ScadaControlCapabilities(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/scada.control.capabilities/003
    """

    FromGNodeAlias: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds
    RelayNodes: List[SpaceheatNodeGt]
    DacNodes: List[SpaceheatNodeGt]
    CommandNodes: List[SpaceheatNodeGt]
    ControlChannels: List[DataChannelGt]
    CommandInterfaces: List[CommandInterface]
    TypeName: Literal["scada.control.capabilities"] = "scada.control.capabilities"
    Version: Literal["003"] = "003"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ActorClassConsistency.
        a. All nodes in RelayNodes SHALL have ActorClass equal to Relay.
        b. All nodes in DacNodes SHALL have ActorClass equal to ZeroTenOutputer.
        c. No node in CommandNodes SHALL have ActorClass equal to Relay or ZeroTenOutputer.
        """
        for n in self.RelayNodes:
            if n.ActorClass != ActorClass.Relay:
                raise ValueError(
                    f"Axiom 1 (ActorClassConsistency) failed: RelayNodes contains {n.Name} with ActorClass {n.ActorClass}!"
                )
        for n in self.DacNodes:
            if n.ActorClass != ActorClass.ZeroTenOutputer:
                raise ValueError(
                    f"Axiom 1 (ActorClassConsistency) failed: DacNodes contains {n.Name} with ActorClass {n.ActorClass}!"
                )
        for n in self.CommandNodes:
            if n.ActorClass in (ActorClass.Relay, ActorClass.ZeroTenOutputer):
                raise ValueError(
                    f"Axiom 1 (ActorClassConsistency) failed: CommandNodes contains {n.Name} with ActorClass {n.ActorClass}!"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: HandleTerminalMatchesName.
        For every node in RelayNodes, DacNodes and CommandNodes, Handle SHALL be
        present and its final dot-separated token SHALL equal Name.
        """
        for n in self.RelayNodes + self.DacNodes + self.CommandNodes:
            if not n.Handle or n.Handle.split(".")[-1] != n.Name:
                raise ValueError(
                    f"Axiom 2 (HandleTerminalMatchesName) failed: {n.Name} Handle {n.Handle!r} must be "
                    f"present and end in {n.Name!r}!"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: AboutNodesAreControlNodes.
        The set of ControlChannels.AboutNodeName values SHALL equal the set of
        RelayNodes.Name and DacNodes.Name values.
        """
        node_names = {n.Name for n in self.RelayNodes + self.DacNodes}
        about_names = {c.AboutNodeName for c in self.ControlChannels}
        if node_names != about_names:
            missing = sorted(node_names - about_names)
            extra = sorted(about_names - node_names)
            raise ValueError(
                "Axiom 3 (AboutNodesAreControlNodes) failed: union(RelayNodes.Name, DacNodes.Name) must equal "
                "set(ControlChannels.AboutNodeName). "
                f"MissingAboutNames={missing} ExtraAboutNames={extra}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: CommandInterfacesCoverTheTree.
        a. The set of CommandInterfaces.ActorName values SHALL equal the set of
        Name values of the nodes in RelayNodes and CommandNodes whose Handle
        does not extend the Handle of any CommandNodes entry (a Handle extends
        another when it equals that Handle followed by a dot and further
        tokens), together with the Name values of the RelayNodes entries that
        have a CommandInterfaces entry with AdminMayTake true.
        b. No two CommandInterfaces entries SHALL share both an ActorName and
        an EventType; a node with more than one command vocabulary carries
        one entry per vocabulary.
        c. Every CommandInterfaces entry with AdminMayTake true SHALL have an
        ActorName equal to the Name of a RelayNodes entry.
        """
        relay_names = {n.Name for n in self.RelayNodes}
        taken = {i.ActorName for i in self.CommandInterfaces if i.AdminMayTake}
        if not taken <= relay_names:
            raise ValueError(
                "Axiom 4 (CommandInterfacesCoverTheTree, clause c) failed: AdminMayTake is "
                f"set on an interface for a node that is not a relay: {sorted(taken - relay_names)}"
            )
        owner_prefixes = [f"{n.Handle}." for n in self.CommandNodes if n.Handle]
        directly_commanded = {
            n.Name
            for n in self.RelayNodes + self.CommandNodes
            if n.Handle and not any(n.Handle.startswith(p) for p in owner_prefixes)
        }
        covered = directly_commanded | taken
        interface_names = [i.ActorName for i in self.CommandInterfaces]
        if set(interface_names) != covered:
            missing = sorted(covered - set(interface_names))
            extra = sorted(set(interface_names) - covered)
            raise ValueError(
                "Axiom 4 (CommandInterfacesCoverTheTree, clause a) failed: CommandInterfaces must "
                "cover exactly the relay and command nodes not under an interior command node, "
                "with the relays admin may take. "
                f"MissingInterfacesFor={missing} ExtraInterfacesFor={extra}"
            )
        keys = [(i.ActorName, i.EventType) for i in self.CommandInterfaces]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "Axiom 4 (CommandInterfacesCoverTheTree, clause b) failed: CommandInterfaces "
                f"(ActorName, EventType) pairs must be unique: {sorted(keys)}"
            )
        return self
