from typing import List, Literal

from gwsproto.enums import ActorClass
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.named_types.gw_state_machine import GwStateMachine
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from pydantic import model_validator
from typing_extensions import Self


class LayoutLite(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/layout.lite/013
    """

    FromGNodeAlias: LeftRightDotStr
    CreatedMs: UTCMilliseconds
    MessageId: UUID4Str
    HardwareLayoutTypeName: LeftRightDotStr
    ZoneList: List[str]
    CriticalZoneList: List[str]
    ShNodes: List[SpaceheatNodeGt]
    DataChannels: List[DataChannelGt]
    DerivedChannels: List[DerivedChannelGt]
    StateMachines: List[GwStateMachine]
    TypeName: Literal["layout.lite"] = "layout.lite"
    Version: Literal["013"] = "013"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Dc Node Consistency. Every AboutNodeName and CapturedByNodeName in a
        DataChannel belongs to an ShNode, and in addition every CapturedByNodeName does
        not have ActorClass NoActor.
        """
        for dc in self.DataChannels:
            if dc.AboutNodeName not in [n.Name for n in self.ShNodes]:
                raise ValueError(
                    f"Axiom 1 (DcNodeConsistency) failed: dc {dc.Name} AboutNodeName {dc.AboutNodeName} not in ShNodes!"
                )
            captured_by_node = next(
                (n for n in self.ShNodes if n.Name == dc.CapturedByNodeName), None
            )
            if not captured_by_node:
                raise ValueError(
                    f"Axiom 1 (DcNodeConsistency) failed: dc {dc.Name} CapturedByNodeName {dc.CapturedByNodeName} not in ShNodes!"
                )
            if captured_by_node.ActorClass == ActorClass.NoActor:
                raise ValueError(
                    f"Axiom 1 (DcNodeConsistency) failed: dc {dc.Name}'s CapturedByNode cannot have ActorClass NoActor!"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: Node Handle Hierarchy Consistency. Every ShNode with a handle containing at least
        two words (separated by '.') has an immediate boss: another ShNode whose handle
        matches the original handle minus its last word.
        """
        existing_handles = {get_handle(node) for node in self.ShNodes}
        for node in self.ShNodes:
            handle = get_handle(node)
            if "." in handle:
                boss_handle = ".".join(handle.split(".")[:-1])
                if boss_handle not in existing_handles:
                    raise ValueError(
                        f"Axiom 2 (NodeHandleHierarchyConsistency) failed: node {node.Name} with handle {handle} missing"
                        " its immediate boss!"
                    )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: CriticalZoneList is a subset of ZoneList
        """
        zone_set = set(self.ZoneList)
        for z in self.CriticalZoneList:
            if z not in zone_set:
                raise ValueError(
                    f"Axiom 3 (CriticalZoneSubset) failed: Critical zone '{z}' is not present in ZoneList."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: Derived Node Consistency. Every CreatedByNodeName in a
        DerivedChannelHGt belongs to an ShNode with an active ActorClass
        """
        for dc in self.DerivedChannels:
            if dc.CreatedByNodeName not in [n.Name for n in self.ShNodes]:
                raise ValueError(
                    f"Axiom 4 (DerivedNodeConsistency) failed: dc {dc.Name} CreatedByNodeName {dc.CreatedByNodeName} not in ShNodes!"
                )
            created_by_node = next(
                (n for n in self.ShNodes if n.Name == dc.CreatedByNodeName), None
            )
            assert created_by_node

            if created_by_node.ActorClass == ActorClass.NoActor:
                raise ValueError(
                    f"Axiom 4 (DerivedNodeConsistency) failed: dc {dc.Name}'s CreatedByNode cannot have ActorClass NoActor!"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: State Machine Node Consistency. Every StateMachines.NodeName
        belongs to an ShNode, and no two StateMachines entries share a NodeName.
        """
        node_names = {n.Name for n in self.ShNodes}
        seen: set[str] = set()
        for machine in self.StateMachines:
            if machine.NodeName not in node_names:
                raise ValueError(
                    f"Axiom 5 (StateMachineNodeConsistency) failed: machine on {machine.NodeName} not in ShNodes!"
                )
            if machine.NodeName in seen:
                raise ValueError(
                    f"Axiom 5 (StateMachineNodeConsistency) failed: two machines declared on {machine.NodeName}!"
                )
            seen.add(machine.NodeName)
        return self

def get_handle(node: SpaceheatNodeGt) -> str:
    if node.Handle:
        return node.Handle
    return node.Name
