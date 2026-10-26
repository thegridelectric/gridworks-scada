from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.data_channel_gt import DataChannelGt
from sema_snapshot.sema.types.derived_channel_gt import DerivedChannelGt
from sema_snapshot.sema.types.spaceheat_node_gt import SpaceheatNodeGt
from sema_snapshot.sema.types.state_machine import StateMachine


class LayoutLite(SemaType):
    """Sema: https://schemas.electricity.works/types/layout.lite/013"""

    from_g_node_alias: LeftRightDot
    created_ms: UTCMilliseconds
    message_id: UUID4Str
    hardware_layout_type_name: LeftRightDot
    zone_list: list[str]
    critical_zone_list: list[str]
    sh_nodes: list[SpaceheatNodeGt]
    data_channels: list[DataChannelGt]
    derived_channels: list[DerivedChannelGt]
    state_machines: list[StateMachine]
    type_name: Literal["layout.lite"] = "layout.lite"
    version: Literal["013"] = "013"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "LayoutLite":
        """
        Axiom 1: DcNodeConsistency
        Every DataChannels.AboutNodeName and DataChannels.CapturedByNodeName SHALL reference an
        existing ShNodes.Name, and every captured-by node SHALL have an active ActorClass.
        """
        node_names = {node.name for node in self.sh_nodes}
        active_actorless = {"NoActor"}
        for channel in self.data_channels:
            if (
                channel.about_node_name not in node_names
                or channel.captured_by_node_name not in node_names
            ):
                raise ValueError(
                    "Axiom 1 failed: data channel node references must exist in sh_nodes."
                )
            captured = next(
                node
                for node in self.sh_nodes
                if node.name == channel.captured_by_node_name
            )
            if str(captured.actor_class) in active_actorless:
                raise ValueError(
                    "Axiom 1 failed: captured-by node must have an active actor class."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "LayoutLite":
        """
        Axiom 2: NodeHandleHierarchyConsistency
        Every ShNode with a dotted handle SHALL have its immediate boss present as another
        ShNode in the same payload.
        """
        node_names = {node.name for node in self.sh_nodes}
        for node in self.sh_nodes:
            if node.handle and "." in node.handle:
                immediate_boss = node.handle.split(".")[-2]
                if immediate_boss not in node_names:
                    raise ValueError(
                        "Axiom 2 failed: missing immediate boss node for handle hierarchy."
                    )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "LayoutLite":
        """
        Axiom 3: CriticalZoneSubset
        CriticalZoneList SHALL be a subset of ZoneList.
        """
        if not set(self.critical_zone_list).issubset(set(self.zone_list)):
            raise ValueError(
                "Axiom 3 failed: critical_zone_list must be a subset of zone_list."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "LayoutLite":
        """
        Axiom 4: DerivedNodeConsistency
        Every DerivedChannels.CreatedByNodeName SHALL reference an existing ShNodes.Name whose
        ActorClass is active.
        """
        nodes = {node.name: node for node in self.sh_nodes}
        for channel in self.derived_channels:
            created_by = nodes.get(channel.created_by_node_name)
            if created_by is None or str(created_by.actor_class) == "NoActor":
                raise ValueError(
                    "Axiom 4 failed: derived channel created_by_node_name must reference an active node."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "LayoutLite":
        """
        Axiom 5: StateMachineNodeConsistency
        Every StateMachines.NodeName SHALL reference an existing ShNodes.Name, and no two
        StateMachines entries SHALL share a NodeName.
        """
        node_names = {node.name for node in self.sh_nodes}
        seen: set[str] = set()
        for machine in self.state_machines:
            if machine.node_name not in node_names:
                raise ValueError(
                    "Axiom 5 failed: state machine node_name must reference an existing sh_node."
                )
            if machine.node_name in seen:
                raise ValueError(
                    "Axiom 5 failed: two state machines declared on one node_name."
                )
            seen.add(machine.node_name)
        return self
