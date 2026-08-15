from typing import List, Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import ActorClass
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ScadaControlCapabilities(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/scada.control.capabilities/001
    """

    FromGNodeAlias: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds
    RelayNodes: List[SpaceheatNodeGt]
    DacNodes: List[SpaceheatNodeGt]
    ControlChannels: List[DataChannelGt]
    I2cRelayComponent: I2cMultichannelDtRelayComponentGt
    TypeName: Literal["scada.control.capabilities"] = "scada.control.capabilities"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ActorClassConsistency.
        a. All nodes in RelayNodes SHALL have ActorClass equal to Relay.
        b. All nodes in DacNodes SHALL have ActorClass equal to ZeroTenOutputer.
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
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: HandleTerminalMatchesName.
        For every node in RelayNodes and DacNodes, Handle SHALL be present and
        its final dot-separated token SHALL equal Name.
        """
        for n in self.RelayNodes + self.DacNodes:
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
        Axiom 4: I2cRelayComponentChannelControlNodeConsistency.
        a. The set of ActorName values in I2cRelayComponent.ConfigList SHALL equal
        the set of RelayNodes.Name values.
        b. For each relay actor config in I2cRelayComponent.ConfigList, ChannelName
        SHALL equal the Name of the ControlChannels entry whose AboutNodeName is
        that relay actor config's ActorName.
        """
        relay_node_names = {n.Name for n in self.RelayNodes}
        config_actor_names = {
            config.ActorName for config in self.I2cRelayComponent.ConfigList
        }
        if relay_node_names != config_actor_names:
            missing = sorted(relay_node_names - config_actor_names)
            extra = sorted(config_actor_names - relay_node_names)
            raise ValueError(
                "Axiom 4 (I2cRelayComponentChannelControlNodeConsistency) failed: "
                "RelayNodes and I2cRelayComponent.ConfigList mismatch. "
                f"MissingConfigsFor={missing} ExtraConfigsFor={extra}"
            )
        channel_by_about_name = {c.AboutNodeName: c for c in self.ControlChannels}
        for config in self.I2cRelayComponent.ConfigList:
            channel = channel_by_about_name.get(config.ActorName)
            if channel is None or config.ChannelName != channel.Name:
                raise ValueError(
                    f"Axiom 4 (I2cRelayComponentChannelControlNodeConsistency) failed: "
                    f"I2cRelayComponent config for {config.ActorName} "
                    f"has ChannelName {config.ChannelName!r}, expected the "
                    f"ControlChannels entry named for AboutNodeName {config.ActorName!r}."
                )
        return self
