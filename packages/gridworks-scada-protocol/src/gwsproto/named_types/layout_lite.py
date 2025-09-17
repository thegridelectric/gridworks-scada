"""Type layout.lite, version 002"""

from typing import List, Literal

from gwproto.enums import ActorClass
from gwproto.named_types.data_channel_gt import DataChannelGt
from gwproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwproto.named_types.pico_flow_module_component_gt import PicoFlowModuleComponentGt
from gwproto.named_types.pico_tank_module_component_gt import PicoTankModuleComponentGt
from gwproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwproto.named_types.synth_channel_gt import SynthChannelGt
from gwproto.property_format import LeftRightDotStr, UTCMilliseconds, UUID4Str
from gwsproto.named_types.ha1_params import Ha1Params
from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self


class LayoutLite(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    FromGNodeInstanceId: UUID4Str
    MessageCreatedMs: UTCMilliseconds
    MessageId: UUID4Str
    Strategy: str
    ZoneList: List[str]
    TotalStoreTanks: PositiveInt
    ShNodes: List[SpaceheatNodeGt]
    DataChannels: List[DataChannelGt]
    SynthChannels: List[SynthChannelGt]
    TankModuleComponents: List[PicoTankModuleComponentGt]
    FlowModuleComponents: List[PicoFlowModuleComponentGt]
    Ha1Params: Ha1Params
    I2cRelayComponent: I2cMultichannelDtRelayComponentGt
    TypeName: Literal["layout.lite"] = "layout.lite"
    Version: str = "004"

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
                    f"dc {dc.Name} AboutNodeName {dc.AboutNodeName} not in ShNodes!"
                )
            captured_by_node = next(
                (n for n in self.ShNodes if n.Name == dc.CapturedByNodeName), None
            )
            if not captured_by_node:
                raise ValueError(
                    f"dc {dc.Name} CapturedByNodeName {dc.CapturedByNodeName} not in ShNodes!"
                )
            if captured_by_node.ActorClass == ActorClass.NoActor:
                raise ValueError(
                    f"dc {dc.Name}'s CatpuredByNode cannot have ActorClass NoActor!"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Node Handle Hierarchy Consistency. Every ShNode with a handle containing at least
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
                        f"node {node.Name} with handle {handle} missing"
                        " its immediate boss!"
                    )
        return self


def get_handle(node: SpaceheatNodeGt) -> str:
    if node.Handle:
        return node.Handle
    return node.Name
