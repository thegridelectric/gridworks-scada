"""Temporary package for assisting generation of hardware_layout.json files"""
import json
import subprocess
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, List
import uuid

from gw.errors import DcError

from gwproto.type_helpers import CACS_BY_MAKE_MODEL
from gwproto.enums import ActorClass
from gwproto.enums import MakeModel
from gwproto.enums import Unit
from gwproto.enums import TelemetryName
from gwproto.named_types import ComponentAttributeClassGt
from gwproto.named_types import ComponentGt
from gwproto.named_types import ElectricMeterCacGt
from gwproto.named_types import SpaceheatNodeGt
from gwproto.named_types import DataChannelGt
from gwproto.named_types import SynthChannelGt
from gwproto.named_types import ElectricMeterChannelConfig
from gwproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from gwproto.property_format import SpaceheatName
from gwproto.data_classes.telemetry_tuple import ChannelStub
from data_classes.house_0_names import H0N, H0CN
from enums import FlowManifoldVariant, HomeAloneStrategy

class ChannelStubDb(ChannelStub):
    CapturedByNodeName: SpaceheatName

ChanneStubDbByName: Dict[str, ChannelStubDb] = {
    H0CN.hp_odu_pwr: ChannelStubDb(
        Name=H0CN.hp_odu_pwr,
        AboutNodeName=H0N.hp_odu,
        TelemetryName=TelemetryName.PowerW,
        InPowerMetering=True,
        CapturedByNodeName=H0N.primary_power_meter,
    ),
    H0CN.hp_idu_pwr: ChannelStubDb(
        Name=H0CN.hp_idu_pwr,
        AboutNodeName=H0N.hp_idu,
        TelemetryName=TelemetryName.PowerW,
        InPowerMetering=True,
        CapturedByNodeName=H0N.primary_power_meter,
    ),
    H0CN.dist_pump_pwr: ChannelStubDb(
        Name=H0CN.dist_pump_pwr,
        AboutNodeName=H0N.dist_pump,
        TelemetryName=TelemetryName.PowerW,
        CapturedByNodeName=H0N.primary_power_meter,
    ),
     H0CN.primary_pump_pwr: ChannelStubDb(
        Name=H0CN.primary_pump_pwr,
        AboutNodeName=H0N.primary_pump,
        TelemetryName=TelemetryName.PowerW,
        CapturedByNodeName=H0N.primary_power_meter,
    ),
    H0CN.store_pump_pwr: ChannelStubDb(
        Name=H0CN.store_pump_pwr,
        AboutNodeName=H0N.store_pump,
        TelemetryName=TelemetryName.PowerW,
        CapturedByNodeName=H0N.primary_power_meter,
    ),

    H0CN.dist_swt: ChannelStubDb(
        Name=H0CN.dist_swt,
        AboutNodeName=H0N.dist_swt,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),
    H0CN.dist_rwt: ChannelStubDb(
        Name=H0CN.dist_rwt,
        AboutNodeName=H0N.dist_rwt,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),
    H0CN.hp_lwt: ChannelStubDb(
        Name=H0CN.hp_lwt,
        AboutNodeName=H0N.hp_lwt,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),
    H0CN.hp_ewt: ChannelStubDb(
        Name=H0CN.hp_ewt,
        AboutNodeName=H0N.hp_ewt,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),
    H0CN.store_hot_pipe: ChannelStubDb(
        Name=H0CN.store_hot_pipe,
        AboutNodeName=H0N.store_hot_pipe,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),
    H0CN.store_cold_pipe: ChannelStubDb(
        Name=H0CN.store_cold_pipe,
        AboutNodeName=H0N.store_cold_pipe,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),
    H0CN.buffer_hot_pipe: ChannelStubDb(
        Name=H0CN.buffer_hot_pipe,
        AboutNodeName=H0N.buffer_hot_pipe,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),
    H0CN.buffer_cold_pipe: ChannelStubDb(
        Name=H0CN.buffer_cold_pipe,
        AboutNodeName=H0N.buffer_cold_pipe,
        TelemetryName=TelemetryName.WaterTempCTimes1000,
        CapturedByNodeName=H0N.analog_temp,
    ),

}


@dataclass
class StubConfig:
    home_alone_strategy: HomeAloneStrategy = HomeAloneStrategy.WinterTou
    flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.House0
    use_sieg_loop: bool = False
    atn_gnode_alias: str = "d1.isone.ct.newhaven.orange1"
    terminal_asset_alias: Optional[str] = None
    zone_list: typing.Sequence[str] = field(default_factory=tuple)
    total_store_tanks: int = 3
    scada_display_name: str = "Dummy Orange Scada"
    add_stub_power_meter: bool = True
    power_meter_cac_alias: str = "Dummy Power Meter Cac"
    power_meter_component_alias: str = "Dummy Power Meter Component"
    power_meter_node_display_name: str = "Dummy Power Meter"
    boost_element_display_name: str = "Dummy Boost Element"
    

class LayoutIDMap:
    REMOTE_HARDWARE_LAYOUT_PATH: str = "/home/pi/.config/gridworks/scada/hardware-layout.json"

    cacs_by_alias: dict[str, str]
    components_by_alias: dict[str, str]
    nodes_by_name: dict[str, str]
    channels_by_name: dict[str, str]
    synth_channels_by_name: dict[str, str]
    gnodes: dict[str, dict]
    zone_list: List[str]
    total_store_tanks: int

    def __init__(self, d: Optional[dict] = None):
        self.cacs_by_alias = {}
        self.components_by_alias = {}
        self.nodes_by_name = {}
        self.channels_by_name = {}
        self.synth_channels_by_name = {}
        self.gnodes = {}
        self.zone_list = []
        self.total_store_tanks = 3
        self.strategy = "House0"
        if not d:
            return
        for k, v in d.items():
                if isinstance(v, dict) and "GNodeId" in v:
                    self.gnodes[k] = v
                if k == "ZoneList":
                    self.zone_list = v
                elif k == "TotalStoreTanks":
                    self.total_store_tanks = v
                elif k == "ShNodes":
                        for node in v:
                            try:
                                self.add_node(
                                    node["ShNodeId"],
                                    node["Name"],
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{node}. Error: {type(e)}, <{e}>"
                                )
                elif k == "DataChannels":
                        for channel in v:
                            try:
                                self.add_channel(
                                    channel["Id"],
                                    channel["Name"]
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{channel}. Error: {type(e)}, <{e}>"
                                )
                elif k == "SynthChannels":
                        for channel in v:
                            try:
                                self.add_synth_channel(
                                    channel["Id"],
                                    channel["Name"]
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{channel}. Error: {type(e)}, <{e}>"
                                )

                elif k.lower().endswith("cacs"):
                        for cac in v:
                            try:
                                self.add_cacs_by_alias(
                                    cac["ComponentAttributeClassId"],
                                    cac["MakeModel"],
                                    cac["DisplayName"],
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{cac}. Error: {type(e)}, <{e}>"
                                )

                elif k.lower().endswith("components"):
                        for component in v:
                            try:
                                self.add_component(
                                    component["ComponentId"],
                                    component["DisplayName"],
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{component}. Error: {type(e)}, <{e}>"
                                )

    def add_cacs_by_alias(self, id_: str, make_model_: str, display_name_: str):
        if make_model_ == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL.value:
            self.cacs_by_alias[display_name_] = id_
        else:
            if CACS_BY_MAKE_MODEL[make_model_] != id_:
                raise DcError(f"MakeModel {make_model_} does not go with {id_}")
            self.cacs_by_alias[make_model_] = id_

    def add_component(self, id_: str, alias: str):
        self.components_by_alias[alias] = id_

    def add_node(self, id_: str, name: str):
        self.nodes_by_name[name] = id_
    
    def add_channel(self, id_: str, name: str):
        self.channels_by_name[name] = id_

    def add_synth_channel(self, id_: str, name: str):
        self.synth_channels_by_name[name] = id_

    @classmethod
    def from_path(cls, path: Path) -> "LayoutIDMap":
        with path.open() as f:
            return LayoutIDMap(json.loads(f.read()))

    @classmethod
    def from_rclone(
        cls, rclone_name: str,
        upload_dir: Path,
        remote_path: str | Path = REMOTE_HARDWARE_LAYOUT_PATH
    ) -> "LayoutIDMap":
        if not upload_dir.exists():
            upload_dir.mkdir(parents=True)
        dest_path = upload_dir / f"{rclone_name}.uploaded.json"
        upload = [
            "rclone",
            "copyto",
            f"{rclone_name}:{str(remote_path)}",
            f"{dest_path}",
        ]
        print(f"Running upload command:\n\n{' '.join(upload)}\n")
        result = subprocess.run(upload, capture_output=True)
        if result.returncode != 0:
            print(f"Command output:\n[\n{result.stderr.decode('utf-8')}\n]")
            raise RuntimeError(
                f"ERROR. Command <{' '.join(upload)}> failed with returncode:{result.returncode}"
            )
        return cls.from_path(dest_path)

class LayoutDb:
    lists: dict[str, list[ComponentAttributeClassGt | ComponentGt | SpaceheatNodeGt | DataChannelGt | SynthChannelGt]]
    cacs_by_id: dict[str, ComponentAttributeClassGt]
    components_by_id: dict[str, ComponentGt]
    nodes_by_id: dict[str, SpaceheatNodeGt]
    channels_by_id: dict[str, DataChannelGt]
    synth_channels_by_id: dict[str, SynthChannelGt]
    loaded: LayoutIDMap
    maps: LayoutIDMap
    misc: dict
    terminal_asset_alias: str

    def __init__(
        self,
        existing_layout: Optional[LayoutIDMap] = None,
        cacs: Optional[list[ComponentAttributeClassGt]] = None,
        components: Optional[list[ComponentGt]] = None,
        nodes: Optional[list[SpaceheatNodeGt]] = None,
        channels: Optional[list[DataChannelGt]] = None,
        synth_channels: Optional[list[SynthChannelGt]] = None,
        add_stubs: bool = False,
        stub_config: Optional[StubConfig] = None,
    ):
        self.lists = dict(OtherComponents=[])
        self.cacs_by_id = {}
        self.components_by_id = {}
        self.component_lists = {}
        self.nodes_by_id = {}
        self.channels_by_id = {}
        self.synth_channels_by_id = {}
        self.misc = {}
        self.loaded = existing_layout or LayoutIDMap()
        self.maps = LayoutIDMap()
        if cacs is not None:
            self.add_cacs(cacs)
        if components is not None:
            self.add_components(components)
        if nodes is not None:
            self.add_nodes(nodes)
        if channels is not None:
            self.add_data_channels(channels)
        if synth_channels is not None:
            self.add_synth_channels(synth_channels)
        
        if add_stubs:
            self.add_stubs(stub_config)
    
    @property
    def terminal_asset_alias(self):
        return self.misc["MyTerminalAssetGNode"]["Alias"]

    def cac_id_by_alias(self, make_model: str) -> Optional[str]:
        return self.maps.cacs_by_alias.get(make_model, None)

    def component_id_by_alias(self, component_alias: str) -> Optional[str]:
        return self.maps.components_by_alias.get(component_alias, None)

    def node_id_by_name(self, node_name: str) -> Optional[str]:
        return self.maps.nodes_by_name.get(node_name, None)
    
    def channel_id_by_name(self, name: str) -> Optional[str]:
        return self.maps.channels_by_name.get(name, None)
    
    def synth_channel_id_by_name(self, name: str) -> Optional[str]:
        return self.maps.synth_channels_by_name.get(name, None)

    @classmethod
    def make_cac_id(cls, make_model: MakeModel) -> str:
        if make_model == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            return str(uuid.uuid4())
        if type(make_model) is str:
            if make_model in CACS_BY_MAKE_MODEL:
                return CACS_BY_MAKE_MODEL[make_model]
            else:
                return str(uuid.uuid4())
        elif make_model.value in CACS_BY_MAKE_MODEL:
            return CACS_BY_MAKE_MODEL[str(make_model.value)]
        else:
            return str(uuid.uuid4())

    def make_component_id(self, component_alias: str) -> str:
        return self.loaded.components_by_alias.get(component_alias, str(uuid.uuid4()))

    def make_node_id(self, node_name: str) -> str:
        return self.loaded.nodes_by_name.get(node_name, str(uuid.uuid4()))
    
    def make_channel_id(self, name: str) -> str:
        return self.loaded.channels_by_name.get(name, str(uuid.uuid4()))
    
    def make_synth_channel_id(self, name: str) -> str:
        return self.loaded.synth_channels_by_name.get(name, str(uuid.uuid4()))

    def add_cacs(self, cacs:list[ComponentAttributeClassGt], layout_list_name: str = "OtherCacs"):
        for cac in cacs:
            if cac.ComponentAttributeClassId in self.cacs_by_id:
                raise ValueError(
                    f"ERROR: cac with id <{cac.ComponentAttributeClassId}> "
                    "already present"
                )
            self.cacs_by_id[cac.ComponentAttributeClassId] = cac
            self.maps.add_cacs_by_alias(
                    cac.ComponentAttributeClassId,
                    cac.MakeModel,
                    cac.DisplayName,
                )

            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(cac)

    def add_components(self, components:list[ComponentGt], layout_list_name: str = "OtherComponents"):
        for component in components:
            if component.ComponentId in self.components_by_id:
                raise ValueError(
                    f"ERROR. Component with id {component.ComponentId} "
                    "already present."
                )
            if component.DisplayName in self.maps.components_by_alias:
                raise ValueError(
                    f"ERROR. Component with DisplayName {component.DisplayName} "
                    "already present."
                )
            self.components_by_id[component.ComponentId] = component
            self.maps.add_component(
                component.ComponentId,
                component.DisplayName,
            )
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(component)

    def add_nodes(self, nodes:list[SpaceheatNodeGt]):
        for node in nodes:
            if node.ShNodeId in self.nodes_by_id:
                raise ValueError(
                    f"ERROR Node id {node.ShNodeId} already present."
                )
            if node.Name in self.maps.nodes_by_name:
                raise ValueError(
                    f"ERROR Node name {node.Name} already present."
                )
            self.nodes_by_id[node.ShNodeId] = node
            self.maps.add_node(node.ShNodeId, node.Name)
            layout_list_name = "ShNodes"
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(node)
    
    def add_data_channels(self, dcs: list[DataChannelGt]):
        for dc in dcs:
            if dc.Id in self.channels_by_id:
                raise ValueError(
                    f"ERROR channel id {dc.Id} already present."
                )
            if dc.Name in self.maps.channels_by_name:
                raise ValueError(
                    f"ERROR Channel name {dc.Name} already present"
                )
            self.channels_by_id[dc.Id] = dc
            self.maps.add_channel(dc.Id, dc.Name)
            layout_list_name = "DataChannels"
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(dc)

    def add_synth_channels(self, scs: list[SynthChannelGt]):
        for sc in scs:
            if sc.Id in self.synth_channels_by_id:
                raise ValueError(
                    f"ERROR synth channel id {sc.Id} already present."
                )
            if sc.Name in self.maps.synth_channels_by_name:
                raise ValueError(
                    f"ERROR Synth Channel name {sc.Name} already present"
                )
            self.synth_channels_by_id[sc.Id] = sc
            self.maps.add_synth_channel(sc.Id, sc.Name)
            layout_list_name = "SynthChannels"
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(sc)
        

    def add_stub_power_meter(self, cfg: Optional[StubConfig] = None):
        if cfg is None:
            cfg = StubConfig()
        if MakeModel.GRIDWORKS__SIMPM1 not in self.maps.cacs_by_alias:
            self.add_cacs(
                [
                    typing.cast(
                        ComponentAttributeClassGt,
                        ElectricMeterCacGt(
                            ComponentAttributeClassId=CACS_BY_MAKE_MODEL[MakeModel.GRIDWORKS__SIMPM1],
                            MakeModel=MakeModel.GRIDWORKS__SIMPM1,
                            DisplayName=cfg.power_meter_cac_alias,
                            TelemetryNameList=[TelemetryName.PowerW],
                            MinPollPeriodMs=1000,
                        )
                    ),
                ],
                "ElectricMeterCacs"
            )
        
        self.add_components(
            [
                typing.cast(
                    ComponentGt,
                    ElectricMeterComponentGt(
                        ComponentId=self.make_component_id(cfg.power_meter_component_alias),
                        ComponentAttributeClassId=self.cac_id_by_alias(MakeModel.GRIDWORKS__SIMPM1),
                        DisplayName=cfg.power_meter_component_alias,
                        ConfigList=[
                            ElectricMeterChannelConfig(
                                ChannelName=H0CN.hp_odu_pwr,
                                PollPeriodMs=1000,
                                CapturePeriodS=300,
                                AsyncCapture=True,
                                AsyncCaptureDelta=200,
                                Exponent=0,
                                Unit=Unit.W,
                            ),
                            ElectricMeterChannelConfig(
                                ChannelName=H0CN.hp_idu_pwr,
                                PollPeriodMs=1000,
                                CapturePeriodS=300,
                                AsyncCapture=True,
                                AsyncCaptureDelta=200,
                                Exponent=0,
                                Unit=Unit.W,
                            ),
                        ],
                    )
                )
            ],
            "ElectricMeterComponents"
        )
        self.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.primary_power_meter),
                    Name=H0N.primary_power_meter,
                    ActorClass=ActorClass.PowerMeter,
                    DisplayName=cfg.power_meter_node_display_name,
                    ComponentId=self.component_id_by_alias(cfg.power_meter_component_alias),
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.hp_odu),
                    Name=H0N.hp_odu,
                    ActorClass=ActorClass.NoActor,
                    DisplayName=cfg.boost_element_display_name,
                    InPowerMetering=True,
                    NameplatePowerW=4500,
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.hp_idu),
                    Name=H0N.hp_idu,
                    ActorClass=ActorClass.NoActor,
                    DisplayName=cfg.boost_element_display_name,
                    InPowerMetering=True,
                    NameplatePowerW=4500,
                ),
            ]
        )
        
        self.add_data_channels(
            [
                DataChannelGt(
                    Name=H0CN.hp_odu_pwr,
                    Id=self.make_channel_id(H0CN.hp_odu_pwr),
                    DisplayName=' '.join(word.capitalize() for word in H0CN.hp_odu_pwr.split('-')) + " Pwr",
                    AboutNodeName=H0N.hp_odu,
                    CapturedByNodeName=H0N.primary_power_meter,
                    TelemetryName=TelemetryName.PowerW,
                    InPowerMetering=True,
                    TerminalAssetAlias=self.terminal_asset_alias
                ),
                DataChannelGt(
                    Name=H0CN.hp_idu_pwr,
                    Id=self.make_channel_id(H0CN.hp_idu_pwr),
                    DisplayName=' '.join(word.capitalize() for word in H0CN.hp_idu_pwr.split('-')) + " Pwr",
                    AboutNodeName=H0N.hp_idu,
                    CapturedByNodeName=H0N.primary_power_meter,
                    TelemetryName=TelemetryName.PowerW,
                    InPowerMetering=True,
                    TerminalAssetAlias=self.terminal_asset_alias
                )
            ]
        )

    def add_stub_scadas(self, cfg: Optional[StubConfig] = None):
        if cfg is None:
            cfg = StubConfig()
        if self.loaded.gnodes:
            self.misc.update(self.loaded.gnodes)
        else:
            self.misc["MyAtomicTNodeGNode"] = {
                "GNodeId": str(uuid.uuid4()),
                "Alias": cfg.atn_gnode_alias,
                "DisplayName": "ATN GNode",
                "GNodeStatusValue": "Active",
                "PrimaryGNodeRoleAlias": "AtomicTNode"
            }
            self.misc["MyScadaGNode"] = {
                "GNodeId": str(uuid.uuid4()),
                "Alias": f"{cfg.atn_gnode_alias}.scada",
                "DisplayName": "Scada GNode",
                "GNodeStatusValue": "Active",
                "PrimaryGNodeRoleAlias": "Scada"
            }
            ta_alias = f"{cfg.atn_gnode_alias}.ta"
            if cfg.terminal_asset_alias:
                ta_alias = cfg.terminal_asset_alias
            self.misc["MyTerminalAssetGNode"] = {
                "GNodeId": str(uuid.uuid4()),
                "Alias": ta_alias,
                "DisplayName": "TerminalAsset GNode",
                "GNodeStatusValue": "Active",
                "PrimaryGNodeRoleAlias": "TerminalAsset"
              }
        if self.loaded.zone_list:
            self.misc["ZoneList"] = self.loaded.zone_list
        else:
            self.misc["ZoneList"] = cfg.zone_list

        if self.loaded.total_store_tanks:
            self.misc["TotalStoreTanks"] = self.loaded.total_store_tanks
        else:
            self.misc["TotalStoreTanks"] =  self.loaded.total_store_tanks
        self.misc["Strategy"] = "House0"
        self.misc["FlowManifoldVariant"] = cfg.flow_manifold_variant
        self.misc["UseSiegLoop"] = cfg.use_sieg_loop
        self.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.primary_scada),
                    Name=H0N.primary_scada,
                    ActorClass=ActorClass.Scada,
                    DisplayName=cfg.scada_display_name,
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.secondary_scada),
                    Name=H0N.secondary_scada,
                    ActorClass=ActorClass.Parentless,
                    DisplayName="Secondary Scada"
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.admin),
                    Name=H0N.admin,
                    Handle=H0N.admin,
                    ActorClass=ActorClass.NoActor,
                    DisplayName="Local Admin",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.auto),
                    Name=H0N.auto,
                    Handle=H0N.auto,
                    ActorClass=ActorClass.NoActor,
                    DisplayName="Auto - FSM for dispatch contract",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.atn),
                    Name=H0N.atn,
                    ActorClass=ActorClass.NoActor,
                    DisplayName="Atn",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.atomic_ally),
                    Name=H0N.atomic_ally,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.atomic_ally}",
                    Handle=f"{H0N.atn}.{H0N.atomic_ally}",
                    ActorClass=ActorClass.AtomicAlly,
                    DisplayName="Atomic Ally",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.synth_generator),
                    Name=H0N.synth_generator,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.synth_generator}",
                    ActorClass=ActorClass.SynthGenerator,
                    DisplayName="Synth Generator",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.home_alone),
                    Name=H0N.home_alone,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.home_alone}",
                    Handle="auto.h",
                    ActorClass=ActorClass.HomeAlone,
                    DisplayName="HomeAlone",
                    Strategy=cfg.home_alone_strategy,
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.home_alone_normal),
                    Name=H0N.home_alone_normal,
                    Handle="auto.h.n",
                    ActorClass=ActorClass.NoActor,
                    DisplayName="HomeAlone Normal",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.home_alone_onpeak_backup),
                    Name=H0N.home_alone_onpeak_backup,
                    Handle="auto.h.onpeak-backup",
                    ActorClass=ActorClass.NoActor,
                    DisplayName="HomeAlone Onpeak Backup",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.home_alone_scada_blind),
                    Name=H0N.home_alone_scada_blind,
                    Handle="auto.h.scada-blind",
                    ActorClass=ActorClass.NoActor,
                    DisplayName="HomeAlone Scada Blind",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.hp_boss),
                    Name=H0N.hp_boss,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.hp_boss}",
                    Handle="auto.h.n.hp-boss",
                    ActorClass=ActorClass.HpBoss,
                    DisplayName="HeatpumpBoss",
                ),
                
            ]
        )
        if cfg.use_sieg_loop:
            self.add_nodes(
                [
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.sieg_loop),
                    Name=H0N.sieg_loop,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.sieg_loop}",
                    Handle=f"{H0N.auto}.{H0N.home_alone}.{H0N.home_alone_normal}.{H0N.sieg_loop}",
                    ActorClass=ActorClass.SiegLoop,
                    DisplayName="Siegenthaler Loop",
                ),
                ]
            )

            self.add_synth_channels(
                [SynthChannelGt(
                Id = self.make_synth_channel_id(H0CN.hp_keep_seconds_x_10),
                Name = H0CN.hp_keep_seconds_x_10,
                CreatedByNodeName = H0N.sieg_loop,
                TelemetryName = TelemetryName.Unknown,
                TerminalAssetAlias = self.terminal_asset_alias,
                Strategy = "Integrate relay motion",
                DisplayName = "Percent keep in the Siegenthaler loop",
                SyncReportMinutes = 1
                )
            ]
            )

    def add_stubs(self, cfg: Optional[StubConfig] = None):
        if cfg is None:
            cfg = StubConfig()
        self.add_stub_scadas(cfg)
        if cfg.add_stub_power_meter:
            self.add_stub_power_meter(cfg)
        

    def dict(self) -> dict:
        d = dict(
            self.misc,
            **{
                list_name: [
                    entry.as_dict() if hasattr(entry, "as_dict") else entry.model_dump(by_alias=True, exclude_none=True) for entry in entries
                ]
                for list_name, entries in self.lists.items()
            }
        )
        return d

    def write(self, path: str | Path) -> None:
        with Path(path).open("w") as f:
            f.write(json.dumps(self.dict(), sort_keys=True, indent=2))