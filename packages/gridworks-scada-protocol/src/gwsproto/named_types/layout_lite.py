from typing import List, Literal

from gwsproto.enums import ActorClass
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwsproto.named_types.pico_flow_module_component_gt import PicoFlowModuleComponentGt
from gwsproto.named_types.pico_tank_module_component_gt import PicoTankModuleComponentGt
from gwsproto.named_types.sim_pico_tank_module_component_gt import SimPicoTankModuleComponentGt
from gwsproto.named_types.tank_temp_calibration_map import TankTempCalibrationMap
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds, UUID4Str
from gwsproto.named_types.ha1_params import Ha1Params
from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self


class LayoutLite(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    MessageCreatedMs: UTCMilliseconds
    MessageId: UUID4Str
    Strategy: str
    ZoneList: List[str]
    CriticalZoneList: List[str]
    TotalStoreTanks: PositiveInt
    ShNodes: List[SpaceheatNodeGt]
    DataChannels: List[DataChannelGt]
    DerivedChannels: List[DerivedChannelGt]
    TankModuleComponents: List[PicoTankModuleComponentGt | SimPicoTankModuleComponentGt]
    FlowModuleComponents: List[PicoFlowModuleComponentGt]
    Ha1Params: Ha1Params
    I2cRelayComponent: I2cMultichannelDtRelayComponentGt
    TMap: TankTempCalibrationMap | None = None
    TypeName: Literal["layout.lite"] = "layout.lite"
    Version: Literal["007"] = "007"

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
                    f"Axiom 1 Viloated: dc {dc.Name} AboutNodeName {dc.AboutNodeName} not in ShNodes!"
                )
            captured_by_node = next(
                (n for n in self.ShNodes if n.Name == dc.CapturedByNodeName), None
            )
            if not captured_by_node:
                raise ValueError(
                    f"Axiom 1 Viloated: dc {dc.Name} CapturedByNodeName {dc.CapturedByNodeName} not in ShNodes!"
                )
            if captured_by_node.ActorClass == ActorClass.NoActor:
                raise ValueError(
                    f"Axiom 1 Viloated: dc {dc.Name}'s CatpuredByNode cannot have ActorClass NoActor!"
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
                        f"Axiom 2 violated: node {node.Name} with handle {handle} missing"
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
                    f"Axiom 3 violated! Critical zone '{z}' is not present in ZoneList."
                )
        return self

def get_handle(node: SpaceheatNodeGt) -> str:
    if node.Handle:
        return node.Handle
    return node.Name
