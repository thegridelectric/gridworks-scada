"""Temporary package for assisting generation of hardware_layout.json files"""
import json
import subprocess
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import uuid

from gw.errors import DcError

from gwproto.type_helpers import CACS_BY_MAKE_MODEL
from gwproto.enums import ActorClass
from gwproto.enums import LocalCommInterface
from gwproto.enums import MakeModel
from gwproto.enums import Role
from gwproto.enums import Unit
from gwproto.enums import TelemetryName
from gwproto.types import ComponentAttributeClassGt
from gwproto.types import ComponentGt
from gwproto.types import ElectricMeterCacGt
from gwproto.types import SpaceheatNodeGt
from gwproto.types import DataChannelGt
from gwproto.types import ElectricMeterChannelConfig
from gwproto.types.electric_meter_component_gt import ElectricMeterComponentGt

from data_classes.house_0 import H0N

@dataclass
class StubConfig:
    atn_gnode_alias: str = "d1.isone.ct.newhaven.orange1"
    scada_display_name: str = "Dummy Orange Scada"
    add_stub_power_meter: bool = True
    power_meter_cac_alias: str = "Dummy Power Meter Cac"
    power_meter_component_alias: str = "Dummy Power Meter Component"
    power_meter_node_display_name: str = "Dummy Power Meter"
    boost_element_display_name: str = "Dummy Boost Element"

class LayoutIDMap:
    cacs_by_alias: dict[str, str]
    components_by_alias: dict[str, str]
    nodes_by_alias: dict[str, str]
    channels_by_name: dict[str, str]
    gnodes: dict[str, dict]

    def __init__(self, d: Optional[dict] = None):
        self.cacs_by_alias = {}
        self.components_by_alias = {}
        self.nodes_by_alias = {}
        self.channels_by_name = {}
        self.gnodes = {}
        if not d:
            return
        for k, v in d.items():
                if isinstance(v, dict) and "GNodeId" in v:
                    self.gnodes[k] = v
                if k == "ShNodes":
                        for node in v:
                            try:
                                self.add_node(
                                    node["ShNodeId"],
                                    node["Alias"],
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

    def add_node(self, id_: str, alias: str):
        self.nodes_by_alias[alias] = id_
    
    def add_channel(self, id_: str, name: str):
        self.channels_by_name[name] = id_

    @classmethod
    def from_path(cls, path: Path) -> "LayoutIDMap":
        with path.open() as f:
            return LayoutIDMap(json.loads(f.read()))

    @classmethod
    def from_rclone(cls, rclone_name: str, upload_dir: Path) -> "LayoutIDMap":
        if not upload_dir.exists():
            upload_dir.mkdir(parents=True)
        dest_path = upload_dir / f"{rclone_name}.uploaded.json"
        upload = [
            "rclone",
            "copyto",
            f"{rclone_name}:/home/pi/.config/gridworks/scada/hardware-layout.json",
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
    lists: dict[str, list[ComponentAttributeClassGt | ComponentGt | SpaceheatNodeGt]]
    cacs_by_id: dict[str, ComponentAttributeClassGt]
    components_by_id: dict[str, ComponentGt]
    nodes_by_id: dict[str, SpaceheatNodeGt]
    channels_by_id: dict[str, DataChannelGt]
    loaded: LayoutIDMap
    maps: LayoutIDMap
    misc: dict

    def __init__(
        self,
        existing_layout: Optional[LayoutIDMap] = None,
        cacs: Optional[list[ComponentAttributeClassGt]] = None,
        components: Optional[list[ComponentGt]] = None,
        nodes: Optional[list[SpaceheatNodeGt]] = None,
        channels: Optional[list[DataChannelGt]] = None,
        add_stubs: bool = False,
        stub_config: Optional[StubConfig] = None,
    ):
        self.lists = dict(OtherComponents=[])
        self.cacs_by_id = {}
        self.components_by_id = {}
        self.component_lists = {}
        self.nodes_by_id = {}
        self.channels_by_id = {}
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
        
        if add_stubs:
            self.add_stubs(stub_config)
        self.terminal_asset_alias = self.misc["MyTerminalAssetGNode"]["Alias"]

    def cac_id_by_alias(self, make_model: str) -> Optional[str]:
        return self.maps.cacs_by_alias.get(make_model, None)

    def component_id_by_alias(self, component_alias: str) -> Optional[str]:
        return self.maps.components_by_alias.get(component_alias, None)

    def node_id_by_alias(self, node_alias: str) -> Optional[str]:
        return self.maps.nodes_by_alias.get(node_alias, None)
    
    def channel_id_by_name(self, name: str) -> Optional[str]:
        return self.maps.channels_by_name.get(name, None)

    def make_cac_id(self, make_model: MakeModel) -> str:
        if make_model == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            return str(uuid.uuid4())
        if type(make_model) is str:
            if make_model in CACS_BY_MAKE_MODEL:
                return CACS_BY_MAKE_MODEL[make_model]
            else:
                return str(uuid.uuid4())
        elif make_model.value in CACS_BY_MAKE_MODEL:
            return CACS_BY_MAKE_MODEL[make_model.value]
        else:
            return str(uuid.uuid4())

    def make_component_id(self, component_alias: str) -> str:
        return self.loaded.components_by_alias.get(component_alias, str(uuid.uuid4()))

    def make_node_id(self, node_alias: str) -> str:
        return self.loaded.nodes_by_alias.get(node_alias, str(uuid.uuid4()))
    
    def make_channel_id(self, name: str) -> str:
        return self.loaded.channels_by_name.get(name, str(uuid.uuid4()))

    def add_cacs(self, cacs:list[ComponentAttributeClassGt], layout_list_name: str = "OtherCacs"):
        for cac in cacs:
            if cac.ComponentAttributeClassId in self.cacs_by_id:
                raise ValueError(
                    f"ERROR: cac with id <{cac.ComponentAttributeClassId}> "
                    "already present"
                )
            self.cacs_by_id[cac.ComponentAttributeClassId] = cac
            if cac.MakeModel in CACS_BY_MAKE_MODEL:
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
            if node.Alias in self.maps.nodes_by_alias:
                raise ValueError(
                    f"ERROR Node alias {node.Alias} already present."
                )
            self.nodes_by_id[node.ShNodeId] = node
            self.maps.add_node(node.ShNodeId, node.Alias)
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
                            Interface=LocalCommInterface.ETHERNET,
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
                                ChannelName="elt1-pwr",
                                PollPeriodMs=1000,
                                CapturePeriodS=300,
                                AsyncCapture=True,
                                AsyncCaptoreDelta=200,
                                Exponent=0,
                                Unit=Unit.W,
                            ),
                        ],
                    )
                )
            ],
            "ElectricMeterComponents"
        )
        power_meter_alias = H0N.primary_power_meter
        boost_element_alias = "elt1"
        self.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(power_meter_alias),
                    Alias=power_meter_alias,
                    Role=Role.PowerMeter,
                    ActorClass=ActorClass.PowerMeter,
                    DisplayName=cfg.power_meter_node_display_name,
                    ComponentId=self.component_id_by_alias(cfg.power_meter_component_alias),
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(boost_element_alias),
                    Alias=boost_element_alias,
                    Role=Role.BoostElement,
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
                    Name=f"{boost_element_alias}-pwr",
                    Id=self.make_channel_id(f"{boost_element_alias}-pwr"),
                    DisplayName=' '.join(word.capitalize() for word in boost_element_alias.split('-')) + " Pwr",
                    AboutNodeName=boost_element_alias,
                    CapturedByNodeName=power_meter_alias,
                    TelemetryName=TelemetryName.PowerW,
                    InPowerMetering=True,
                    TerminalAssetAlias= "hog" # self.terminal_asset_alias
                )
            ]
        )

    def add_stub_scada(self, cfg: Optional[StubConfig] = None):
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
            self.misc["MyTerminalAssetGNode"] = {
                "GNodeId": str(uuid.uuid4()),
                "Alias": f"{cfg.atn_gnode_alias}.ta",
                "DisplayName": "TerminalAsset GNode",
                "GNodeStatusValue": "Active",
                "PrimaryGNodeRoleAlias": "TerminalAsset"
              }

        self.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.scada),
                    Alias=H0N.scada,
                    Role=Role.Scada,
                    ActorClass=ActorClass.Scada,
                    DisplayName=cfg.scada_display_name,
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.home_alone),
                    Alias=H0N.home_alone,
                    Role=Role.HomeAlone,
                    ActorClass=ActorClass.HomeAlone,
                    DisplayName="HomeAlone",
                )
            ]
        )

    def add_stubs(self, cfg: Optional[StubConfig] = None):
        if cfg is None:
            cfg = StubConfig()
        if cfg.add_stub_power_meter:
            self.add_stub_power_meter(cfg)
        self.add_stub_scada(cfg)

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