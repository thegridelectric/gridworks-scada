from typing import List, Literal

from gwsproto.enums import ActorClass
from gwsproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwsproto.property_format import (
    HandleName,
    LeftRightDotStr,
    SpaceheatName,
    UTCMilliseconds,
)
from pydantic import BaseModel,  model_validator
from typing_extensions import Self


class ControlNode(BaseModel):
    Name: SpaceheatName
    Handle: HandleName
    ActorClass: ActorClass
    DisplayName: str | None = None


class ControlChannel(BaseModel):
    Name: str
    AboutNodeName: SpaceheatName


class ScadaControlCapabilities(BaseModel):
    """Sema: https://schemas.electricity.works/types/scada.control.capabilities/000"""

    FromGNodeAlias: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds

    RelayNodes: List[ControlNode]
    DacNodes: List[ControlNode]
    ControlChannels: List[ControlChannel]

    I2cRelayComponent: I2cMultichannelDtRelayComponentGt

    TypeName: Literal["scada.control.capabilities"] = "scada.control.capabilities"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: RelayNodeClassConsistency
        All nodes in RelayNodes SHALL have ActorClass equal to Relay.
        """
        for n in self.RelayNodes:
            if n.ActorClass != ActorClass.Relay:
                raise ValueError(
                    f"Axiom 1 violated: RelayNodes contains {n.Name} with ActorClass {n.ActorClass}!"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: DacNodeClassConsistency
        All nodes in DacNodes SHALL have ActorClass equal to ZeroTenOutputer.
        """
        for n in self.DacNodes:
            if n.ActorClass != ActorClass.ZeroTenOutputer:
                raise ValueError(
                    f"Axiom 2 violated: DacNodes contains {n.Name} with ActorClass {n.ActorClass}!"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: UniqueRelayNodeNames
        Name values in RelayNodes SHALL be unique.
        """
        names = [n.Name for n in self.RelayNodes]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Axiom 3 violated: duplicate relay node names in RelayNodes: {names}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: UniqueDacNodeNames
        Name values in DacNodes SHALL be unique.
        """
        names = [n.Name for n in self.DacNodes]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Axiom 4 violated: duplicate DAC node names in DacNodes: {names}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: UniqueControlChannelAboutNames
        AboutNodeName values in ControlChannels SHALL be unique.
        """
        about_names = [c.AboutNodeName for c in self.ControlChannels]
        if len(about_names) != len(set(about_names)):
            raise ValueError(
                f"Axiom 5 violated: duplicate AboutNodeName values in ControlChannels: {about_names}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> Self:
        """
        Axiom 6: ControlNodeChannelBijection
        The set of node names defined by the union of RelayNodes.Name and DacNodes.Name
        SHALL equal exactly the set of ControlChannels.AboutNodeName values.
        """
        relay_names = [n.Name for n in self.RelayNodes]
        dac_names = [n.Name for n in self.DacNodes]
        all_node_names = relay_names + dac_names

        # This also enforces no overlap between RelayNodes and DacNodes.
        if len(all_node_names) != len(set(all_node_names)):
            raise ValueError(
                "Axiom 6 violated: RelayNodes.Name and DacNodes.Name overlap or contain duplicates!"
                f" RelayNames={relay_names} DacNames={dac_names}"
            )

        node_set = set(all_node_names)
        about_set = {c.AboutNodeName for c in self.ControlChannels}

        if node_set != about_set:
            missing = sorted(node_set - about_set)
            extra = sorted(about_set - node_set)
            raise ValueError(
                "Axiom 6 violated: union(RelayNodes.Name, DacNodes.Name) must equal "
                "set(ControlChannels.AboutNodeName). "
                f"MissingAboutNames={missing} ExtraAboutNames={extra}"
            )

        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> Self:
        """
        Axiom 7: RelayConfigNodeBijection
        The set of ActorName values in I2cRelayComponent.ConfigList
        SHALL equal exactly the set of RelayNodes.Name values.
        """
        relay_node_set = {n.Name for n in self.RelayNodes}
        config_actor_set = {
            config.ActorName for config in self.I2cRelayComponent.ConfigList
        }

        if relay_node_set != config_actor_set:
            missing_configs = sorted(relay_node_set - config_actor_set)
            extra_configs = sorted(config_actor_set - relay_node_set)
            raise ValueError(
                "Axiom 7 violated: RelayNodes and I2cRelayComponent.ConfigList mismatch. "
                f"MissingConfigsFor={missing_configs} ExtraConfigsFor={extra_configs}"
            )

        return self
