# # Node Ids are going to become the immutable identifiers.
# #
# import typing
# import uuid
# from dataclasses import dataclass
# from typing import Dict, List, Optional

# from gwproto.enums import ActorClass, MakeModel, TelemetryName, Unit
# from gwproto.type_helpers import CACS_BY_MAKE_MODEL
# from gwproto.named_types import (
#     ChannelConfig,
#     ComponentAttributeClassGt,
#     ComponentGt,
#     DataChannelGt,
#     ElectricMeterCacGt,
#     SpaceheatNodeGt,
# )
# from gwproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
# from pydantic import BaseModel

# from gwsproto.data_classes.house_0_names import H0N
# from gwproto.data_classes.house_0_layout import  House0StartHandles

# from layout_gen.layout_db import LayoutDb, LayoutIDMap

# SCADA_2_PARENT_NAME = "s2"

# class ChStub(BaseModel):
#     ChannelName: str
#     AboutName: str
#     TelemetryName: TelemetryName
#     DisplayName: str


# class House0ChStubs:
#     power: List[ChStub]
#     core_temp: List[ChStub]
#     flow: List[ChStub]
#     zone: Dict[str, List[ChStub]]
#     misc: List[ChStub]

#     def __init__(self, total_store_tanks: int, zone_list: List[str]):
#         NAMES = H0N(total_store_tanks, zone_list)

#         self.misc = []
#         self.power = [
#             ChStub(
#                 ChannelName=f"{NAMES.HP_ODU}-pwr",
#                 AboutName=NAMES.HP_ODU,
#                 TelemetryName=TelemetryName.PowerW,
#                 DisplayName="HP ODU Power",
#             ),
#             ChStub(
#                 ChannelName=f"{NAMES.HP_IDU}-pwr",
#                 AboutName=NAMES.HP_IDU,
#                 TelemetryName=TelemetryName.PowerW,
#                 DisplayName="HP IDU Power",
#             ),
#             ChStub(
#                 ChannelName=f"{NAMES.PRIMARY_PUMP}-pwr",
#                 AboutName=NAMES.PRIMARY_PUMP,
#                 TelemetryName=TelemetryName.PowerW,
#                 DisplayName="Primary Pump Power",
#             ),
#             ChStub(
#                 ChannelName=f"{NAMES.DIST_PUMP}-pwr",
#                 AboutName=NAMES.DIST_PUMP,
#                 TelemetryName=TelemetryName.PowerW,
#                 DisplayName="Dist Pump Power",
#             ),
#             ChStub(
#                 ChannelName=f"{NAMES.STORE_PUMP}-pwr",
#                 AboutName=NAMES.STORE_PUMP,
#                 TelemetryName=TelemetryName.PowerW,
#                 DisplayName="Store Pump Power",
#             ),
#         ]

#         self.core_temp = [
#             ChStub(
#                 ChannelName=NAMES.DIST_SWT,
#                 AboutName=NAMES.DIST_SWT,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Dist Source Water Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.DIST_RWT,
#                 AboutName=NAMES.DIST_RWT,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Dist Return Water Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.HP_LWT,
#                 AboutName=NAMES.HP_LWT,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Heat Pump Leaving Water Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.HP_EWT,
#                 AboutName=NAMES.HP_EWT,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Heat Pump Entering Water Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.STORE_HOT_PIPE,
#                 AboutName=NAMES.STORE_HOT_PIPE,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Store Hot Pipe Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.STORE_COLD_PIPE,
#                 AboutName=NAMES.STORE_COLD_PIPE,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Store Cold Pipe Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.BUFFER_HOT_PIPE,
#                 AboutName=NAMES.BUFFER_HOT_PIPE,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Buffer Hot Pipe Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.BUFFER_COLD_PIPE,
#                 AboutName=NAMES.BUFFER_COLD_PIPE,
#                 TelemetryName=TelemetryName.WaterTempCTimes1000,
#                 DisplayName="Buffer Cold Pipe Temp",
#             ),
#             ChStub(
#                 ChannelName=NAMES.TEMP.OAT,
#                 AboutName=NAMES.TEMP.OAT,
#                 TelemetryName=TelemetryName.AirTempCTimes1000,
#                 DisplayName="Outside Air Temp",
#             ),
#         ],
#         self.flow = [
#             ChStub(
#                 ChannelName=NAMES.DIST_FLOW,
#                 AboutName=NAMES.DIST_FLOW,
#                 TelemetryName=TelemetryName.GpmTimes100,
#                 DisplayName="Distribution Flow (Gpm Times 100)",
#             ),
#             ChStub(
#                 ChannelName=NAMES.PRIMARY_FLOW,
#                 AboutName=NAMES.PRIMARY_FLOW,
#                 TelemetryName=TelemetryName.GpmTimes100,
#                 DisplayName="Primary Flow (Gpm Times 100)",
#             ),
#             ChStub(
#                 ChannelName=NAMES.STORE_FLOW,
#                 AboutName=NAMES.STORE_FLOW,
#                 TelemetryName=TelemetryName.GpmTimes100,
#                 DisplayName="Store Flow (Gpm Times 100)",
#             ),
#         ]
#         self.zone = {}
#         for zone_name in NAMES.TEMP.ZONE_LIST:  # e.g. zone1-downstairs
#             self.zone[zone_name] = [
#                 ChStub(
#                     ChannelName=f"{zone_name}-stat-temp".lower(),
#                     AboutName=zone_name,
#                     TelemetryName=TelemetryName.AirTempFTimes1000,
#                     DisplayName=f"Wall Stat Temp for {zone_name}",
#                 ),
#                 ChStub(
#                     ChannelName=f"{zone_name}-setpt".lower(),
#                     AboutName=zone_name,
#                     TelemetryName=TelemetryName.AirTempFTimes1000,
#                     DisplayName=f"Setpoint for {zone_name}",
#                 ),
#             ]

#     def __repr__(self):
#         val = "Power Channels\n"
#         for ch in self.power:
#             val += f"  {ch.ChannelName} ({ch.DisplayName}): reads {ch.TelemetryName.value} of ShNode {ch.AboutName}\n"
#         val += "\n\nCore Temp Channels:\n"
#         for ch in self.core_temp:
#             val += f"  {ch.ChannelName} ({ch.DisplayName}): reads {ch.TelemetryName.value} of ShNode {ch.AboutName}\n"
#         val += "\n\nThermostat Zone Channels:\n"
#         for zone_name in self.zone:
#             for ch in self.zone[zone_name]:
#                 val += f"    {ch.ChannelName} ({ch.DisplayName}): reads {ch.TelemetryName.value} of ShNode {ch.AboutName}\n"

#         return val


# @dataclass
# class House0StubConfig:
#     add_stub_scada: bool = True
#     add_stub_george_hack: bool = False
#     george_hack_display_name: str = "George Hack: First automated control node"
#     atn_gnode_alias: str = ("dummy.atn.gnode",)
#     scada_gnode_alias: str = ("dummy.scada.gnode",)
#     scada_display_name: str = "Dummy Scada"
#     add_stub_power_meter: bool = True
#     power_meter_cac_display_name: str = "Dummy Power Meter Cac"
#     power_meter_component_display_name: str = "Dummy Power Meter Component"
#     power_meter_node_display_name: str = "Dummy Power Meter"
#     hp_pwr_display_name: str = "Dummy Heat Pump"


# class House0LayoutDb(LayoutDb):
#     names: H0N
#     handles: House0StartHandles
#     channel_stubs: House0ChStubs

#     def __init__(
#         self,
#         existing_layout: Optional[LayoutIDMap] = None,
#         cacs: Optional[list[ComponentAttributeClassGt]] = None,
#         components: Optional[list[ComponentGt]] = None,
#         nodes: Optional[list[SpaceheatNodeGt]] = None,
#         channels: Optional[list[DataChannelGt]] = None,
#         add_stubs: bool = False,
#         stub_config: Optional[House0StubConfig] = None,
#         total_store_tanks: int = 3,
#         zone_list: List[str] = ["single"],
#     ):
#         super().__init__(
#             existing_layout=existing_layout,
#             cacs=cacs,
#             components=components,
#             nodes=nodes,
#             channels=channels,
#         )
#         self.total_store_tanks = total_store_tanks
#         self.zone_list = zone_list
#         self.names = H0N(total_store_tanks, zone_list)
#         self.handles = House0StartHandles
#         self.channel_stubs = House0ChStubs(total_store_tanks, zone_list)
#         if add_stubs:
#             self.add_stubs(stub_config)

#     def add_stubs(self, cfg: Optional[House0StubConfig] = None):
#         if cfg is None:
#             cfg = House0StubConfig()
#         if cfg.add_stub_scada:
#             self.add_stub_scada(cfg)
#         if cfg.add_stub_power_meter:
#             self.add_stub_power_meter(cfg)

#     def add_stub_scada(self, cfg: Optional[House0StubConfig] = None):
#         if cfg is None:
#             cfg = House0StubConfig()
#         if self.loaded.gnodes:
#             self.misc.update(self.loaded.gnodes)
#         else:
#             self.misc["MyAtomicTNodeGNode"] = {
#                 "GNodeId": str(uuid.uuid4()),
#                 "Alias": cfg.atn_gnode_alias,
#                 "DisplayName": "ATN GNode",
#                 "GNodeStatusValue": "Active",
#                 "PrimaryGNodeRoleAlias": "AtomicTNode",
#             }
#             self.misc["MyScadaGNode"] = {
#                 "GNodeId": str(uuid.uuid4()),
#                 "Alias": cfg.scada_gnode_alias,
#                 "DisplayName": "Scada GNode",
#                 "GNodeStatusValue": "Active",
#                 "PrimaryGNodeRoleAlias": "Scada",
#             }
#             self.misc["MyTerminalAssetGNode"] = {
#                 "GNodeId": str(uuid.uuid4()),
#                 "Alias": "dummy.ta",
#                 "DisplayName": "Dummy TerminalAsset",
#                 "GNodeStatusValue": "Active",
#                 "PrimaryGNodeRoleAlias": "TerminalAsset",
#             }

#         self.add_nodes(
#             [
#                 SpaceheatNodeGt(
#                     ShNodeId=self.make_node_id(self.names.scada),
#                     Name=self.names.scada,
#                     Handle=self.handles.scada,
#                     ActorClass=ActorClass.Scada,
#                     DisplayName=cfg.scada_display_name,
#                     Strategy="House0",
#                     ZoneList=self.zone_list,
#                     TotalStoreTanks=self.total_store_tanks,
#                 ),
#                 SpaceheatNodeGt(
#                     ShNodeId=self.make_node_id(self.names.home_alone),
#                     Name=self.names.home_alone,
#                     Handle=self.handles.home_alone,
#                     ActorClass=ActorClass.HomeAlone,
#                     DisplayName="HomeAlone",
#                 ),
#                 SpaceheatNodeGt(
#                     ShNodeId=self.make_node_id(SCADA_2_PARENT_NAME),
#                     Name=SCADA_2_PARENT_NAME,
#                     Handle=SCADA_2_PARENT_NAME,
#                     ActorClass=ActorClass.Parentless,
#                     DisplayName="Scada 2",
#                 )
#             ]
#         )

#     def add_stub_power_meter(self, cfg: Optional[House0StubConfig] = None):
#         if cfg is None:
#             cfg = House0StubConfig()
#         if not self.cac_id_by_make_model(MakeModel.GRIDWORKS__SIMPM1):
#             self.add_cacs(
#                 [
#                     typing.cast(
#                         ComponentAttributeClassGt,
#                         ElectricMeterCacGt(
#                             ComponentAttributeClassId=CACS_BY_MAKE_MODEL[
#                                 MakeModel.GRIDWORKS__SIMPM1
#                             ],
#                             MakeModel=MakeModel.GRIDWORKS__SIMPM1,
#                             DisplayName=cfg.power_meter_cac_display_name,
#                             TelemetryNameList=[TelemetryName.PowerW],
#                             MinPollPeriodMs=1000,
#                         ),
#                     ),
#                 ],
#                 "ElectricMeterCacs",
#             )
#         self.add_components(
#             [
#                 typing.cast(
#                     ComponentGt,
#                     ElectricMeterComponentGt(
#                         ComponentId=self.make_component_id(
#                             cfg.power_meter_component_display_name
#                         ),
#                         ComponentAttributeClassId=CACS_BY_MAKE_MODEL[
#                             MakeModel.GRIDWORKS__SIMPM1
#                         ],
#                         DisplayName=cfg.power_meter_component_display_name,
#                         ConfigList=[
#                             ChannelConfig(
#                                 ChannelName="hp-idu-pwr",
#                                 PollPeriodMs=1000,
#                                 CapturePeriodS=60,
#                                 AsyncCapture=True,
#                                 AsyncCaptureDelta=20,
#                                 Exponent=1,
#                                 Unit=Unit.W,
#                             )
#                         ],
#                         EgaugeIoList=[],
#                     ),
#                 )
#             ],
#             "ElectricMeterComponents",
#         )

#         self.add_nodes(
#             [
#                 SpaceheatNodeGt(
#                     ShNodeId=self.make_node_id(
#                         f"s.{self.names.primary_power_meter}"
#                     ),
#                     Name=self.names.primary_power_meter,
#                     ActorClass=ActorClass.PowerMeter,
#                     DisplayName=cfg.power_meter_node_display_name,
#                     ComponentId=self.component_id_by_display_name(
#                         cfg.power_meter_component_display_name
#                     ),
#                 ),
#                 SpaceheatNodeGt(
#                     ShNodeId=self.make_node_id(self.names.hp_idu),
#                     Name=self.names.hp_idu,
#                     ActorClass=ActorClass.NoActor,
#                     DisplayName=cfg.hp_pwr_display_name,
#                     InPowerMetering=True,
#                 ),
#             ]
#         )
