"""Temporary package for assisting generation of hardware_layout.json files"""
import json
import subprocess
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, List, Sequence
import uuid

from gwsproto.errors import DcError

from gwsproto.named_types import ComponentAttributeClassGt
from gwsproto.named_types import ComponentGt
from gwsproto.named_types import ElectricMeterCacGt
from gwsproto.named_types import SpaceheatNodeGt
from gwsproto.named_types import DataChannelGt
from gwsproto.named_types import ElectricMeterChannelConfig
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from gwsproto.data_classes.house_0_names import H0N, H0CN
from gwsproto.enums import (
    ActorClass, EmissionMethod, FlowManifoldVariant, Gw1DeviceType, GwUnit, GwQuantity,
    TelemetryName, Unit,
)
from gwsproto.named_types import (
    DerivedChannelGt,
    LinearOneDimensionalCalibration,
    RequiredEnergyLayered,
    TankTempCalibration,
    TankTempCalibrationMap,
    UsableEnergyLayered,
)


@dataclass
class StubConfig:
    flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.House0
    use_sieg_loop: bool = False
    primary_flow_source: str = "Measured"  # "Measured" | "DerivedSiegSum"
    ltn_gnode_alias: str = "ltn.orange"
    terminal_asset_alias: Optional[str] = None
    zone_list: typing.Sequence[str] = field(default_factory=tuple)
    critical_zone_list: typing.Sequence[str] = field(default_factory=tuple)
    zone_kwh_per_deg_f_list: typing.Sequence[float] = field(default_factory=tuple)
    total_store_tanks: int = 3
    scada_display_name: str = "Dummy Orange Scada"
    add_stub_power_meter: bool = True
    power_meter_cac_alias: str = "Dummy Power Meter Cac"
    power_meter_component_alias: str = "Dummy Power Meter Component"
    power_meter_node_display_name: str = "Dummy Power Meter"
    boost_element_display_name: str = "Dummy Boost Element"
    

class LayoutIDMap:
    REMOTE_HARDWARE_LAYOUT_PATH: str = "/home/pi/.config/gridworks/scada/hardware-layout.json"

    device_type_records: set[str]
    components_by_alias: dict[str, str]
    nodes_by_name: dict[str, str]
    channels_by_name: dict[str, str]
    derived_channels_by_name: dict[str, str]
    zone_list: List[str]
    critical_zone_list: List[str]
    zone_kwh_per_deg_f_list: List[float]
    total_store_tanks: int

    def __init__(self, d: Optional[dict] = None):
        self.device_type_records = set()
        self.components_by_alias = {}
        self.nodes_by_name = {}
        self.channels_by_name = {}
        self.derived_channels_by_name = {}
        self.gnodes: dict[str, dict] = {}
        self.zone_list = []
        self.critical_zone_list = []
        self.zone_kwh_per_deg_f_list = []
        self.total_store_tanks = 3
        self.strategy = "House0"
        if not d:
            return
        for k, v in d.items():
                if isinstance(v, dict) and "GNodeId" in v:
                    self.gnodes[k] = v
                if k == "ZoneList":
                    self.zone_list = v
                elif k == "CriticalZoneList":
                    self.critical_zone_list = v
                elif k == "ZoneKwhPerDegFList":
                    self.zone_kwh_per_deg_f_list = v
                elif k == "TotalStoreTanks":
                    self.total_store_tanks = v
                elif k == "Strategy":
                    self.strategy = v
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
                elif k == "DerivedChannels":
                        for channel in v:
                            try:
                                self.add_derived_channel(
                                    channel["Id"],
                                    channel["Name"]
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{channel}. Error: {type(e)}, <{e}>"
                                )

                elif k.lower().endswith("cacs"):
                        for cac in v:
                            # Tolerant of pre-migration src (cacs keyed by the old
                            # ComponentAttributeClassId with no DeviceType): only device-type
                            # records are tracked now; skip records that predate DeviceType.
                            dt = cac.get("DeviceType")
                            if dt is not None:
                                self.add_device_type_record(dt)

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

    def add_device_type_record(self, device_type: str):
        self.device_type_records.add(device_type)

    def add_component(self, id_: str, alias: str):
        self.components_by_alias[alias] = id_

    def add_node(self, id_: str, name: str):
        self.nodes_by_name[name] = id_
    
    def add_channel(self, id_: str, name: str):
        self.channels_by_name[name] = id_

    def add_derived_channel(self, id_: str, name: str):
        self.derived_channels_by_name[name] = id_

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

    def __init__(
        self,
        existing_layout: LayoutIDMap | None = None,
        add_stubs: bool = False,
        stub_config: Optional[StubConfig] = None,
        *,
        tmap: TankTempCalibrationMap | None = None,
    ):
        self.lists: dict[
            str,
            list[
                ComponentAttributeClassGt
                | ComponentGt
                | SpaceheatNodeGt
                | DataChannelGt
                | DerivedChannelGt
            ]] = {}
        self.misc: dict[str, Any] = {}

        # TEMPORARY: gwproto HardwareLayout still expects SynthChannels.
        # DerivedChannels are the real mechanism going forward.
        self.lists["SynthChannels"] = []

        self.lists["OtherComponents"] = []
        self.cacs_by_id: dict[str, ComponentAttributeClassGt] = {}
        self.components_by_id: dict[str, ComponentGt] = {}
        self.component_lists = {}
        self.nodes_by_id: dict[str, SpaceheatNodeGt] = {}
        self.channels_by_id: dict[str, DataChannelGt] = {}
        self.derived_channels_by_id: dict[str, DerivedChannelGt] = {}
        self.misc = {}
        self.loaded = existing_layout or LayoutIDMap()
        self.maps = LayoutIDMap()

        if add_stubs:
            self.add_stubs(stub_config,tmap=tmap)
    
    @property
    def terminal_asset_alias(self):
        return self.misc["MyTerminalAssetGNode"]["Alias"]

    @property
    def h0cn(self) -> H0CN:
        return H0CN(
            total_store_tanks = self.loaded.total_store_tanks,
            zone_list=list(self.loaded.zone_list),
        )

    def has_device_type_record(self, device_type: str) -> bool:
        return device_type in self.maps.device_type_records

    def component_id_by_alias(self, component_alias: str) -> Optional[str]:
        return self.maps.components_by_alias.get(component_alias, None)

    def node_id_by_name(self, node_name: str) -> Optional[str]:
        return self.maps.nodes_by_name.get(node_name, None)
    
    def channel_id_by_name(self, name: str) -> Optional[str]:
        return self.maps.channels_by_name.get(name, None)
    
    def derived_channel_id_by_name(self, name: str) -> Optional[str]:
        return self.maps.derived_channels_by_name.get(name, None)

    def make_component_id(self, component_alias: str) -> str:
        return self.loaded.components_by_alias.get(component_alias, str(uuid.uuid4()))

    def make_node_id(self, node_name: str) -> str:
        return self.loaded.nodes_by_name.get(node_name, str(uuid.uuid4()))
    
    def make_channel_id(self, name: str) -> str:
        return self.loaded.channels_by_name.get(name, str(uuid.uuid4()))
    
    def make_derived_channel_id(self, name: str) -> str:
        return self.loaded.derived_channels_by_name.get(name, str(uuid.uuid4()))

    def add_cacs(self, cacs:list[ComponentAttributeClassGt], layout_list_name: str = "OtherCacs"):
        for cac in cacs:
            if cac.DeviceType in self.cacs_by_id:
                raise ValueError(
                    f"ERROR: device-type record <{cac.DeviceType}> already present"
                )
            self.cacs_by_id[cac.DeviceType] = cac
            self.maps.add_device_type_record(cac.DeviceType)

            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(cac)

    def add_components(self, components: Sequence[ComponentGt], layout_list_name: str = "OtherComponents"):
        for component in components:
            if not component.DisplayName:
                raise DcError(f"component {component.ComponentId} missing display name! need that for layout gen ...")
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

    def add_derived_channels(self, dcs: list[DerivedChannelGt]):
        for dc in dcs:
            if dc.Id in self.derived_channels_by_id:
                raise ValueError(
                    f"ERROR derived channel id {dc.Id} already present."
                )
            if dc.Name in self.maps.derived_channels_by_name:
                raise ValueError(
                    f"ERROR Derived Channel name {dc.Name} already present"
                )
            self.derived_channels_by_id[dc.Id] = dc
            self.maps.add_derived_channel(dc.Id, dc.Name)
            layout_list_name = "DerivedChannels"
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(dc)

    def add_stub_power_meter(self, cfg: Optional[StubConfig] = None):
        if cfg is None:
            cfg = StubConfig()
        if not self.has_device_type_record(Gw1DeviceType.GridworksSimPowerMeter):
            self.add_cacs(
                [
                    typing.cast(
                        ComponentAttributeClassGt,
                        ElectricMeterCacGt(
                            DeviceType=Gw1DeviceType.GridworksSimPowerMeter,
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
                        DeviceType=Gw1DeviceType.GridworksSimPowerMeter,
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
                    Quantity=GwQuantity.Power,
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
                    Quantity=GwQuantity.Power,
                    InPowerMetering=True,
                    TerminalAssetAlias=self.terminal_asset_alias
                )
            ]
        )

    def add_stub_scadas(
            self,
            cfg: Optional[StubConfig] = None,
            *,
            tmap: TankTempCalibrationMap | None = None,
        ):
        if tmap is None:
            tmap = TankTempCalibrationMap(
                Buffer=TankTempCalibration(),
                Tank={
                    i: TankTempCalibration()
                    for i in range(1, self.loaded.total_store_tanks + 1)
                },
            )
        else:
            expected = self.loaded.total_store_tanks
            actual = len(tmap.Tank)

            if actual != expected:
                raise ValueError(
                    "TankTempCalibrationMap mismatch with layout: "
                    f"layout has {expected} tanks, "
                    f"but calibration map has {actual}"
                )

        if cfg is None:
            cfg = StubConfig()
        if self.loaded.gnodes:
            self.misc.update(self.loaded.gnodes)
        else:
            self.misc["MyLeafTransactiveNodeGNode"] = {
                "GNodeId": str(uuid.uuid4()),
                "Alias": cfg.ltn_gnode_alias,
                "BaseClass": "LeafTransactiveNode",
                "GNodeClass": "LeafTransactiveNode",
                "Status": "Active",
                "PositionPointId": str(uuid.uuid4()),
                "DisplayName": "LeafTransactiveNode",
                "TypeName": "g.node.gt",
                "Version": "004",
            }
            self.misc["MyScadaGNode"] = {
                "GNodeId": str(uuid.uuid4()),
                "Alias": f"{cfg.ltn_gnode_alias}.scada",
                "BaseClass": "Logical",
                "GNodeClass": "Scada",
                "Status": "Active",
                "DisplayName": "Scada GNode",
                "TypeName": "g.node.gt",
                "Version": "004",
            }
            ta_alias = f"{cfg.ltn_gnode_alias}.ta"
            if cfg.terminal_asset_alias:
                ta_alias = cfg.terminal_asset_alias
            self.misc["MyTerminalAssetGNode"] = {
                "GNodeId": str(uuid.uuid4()),
                "Alias": ta_alias,
                "BaseClass": "TerminalAsset",
                "GNodeClass": "TerminalAsset",
                "Status": "Active",
                "PositionPointId": str(uuid.uuid4()),
                "DisplayName": "TerminalAsset GNode",
                "TypeName": "g.node.gt",
                "Version": "004",
            }
        # Flat hydronic keys the per-device builders read during generation; the
        # output (db.dict) folds them into the typed nested "Hydronic" block.
        if self.loaded.zone_list:
            self.misc["ZoneList"] = self.loaded.zone_list
        else:
            self.misc["ZoneList"] = cfg.zone_list
        if self.loaded.critical_zone_list:
            self.misc["CriticalZoneList"] = self.loaded.critical_zone_list
        else:
            self.misc["CriticalZoneList"] = cfg.critical_zone_list
        if self.loaded.zone_kwh_per_deg_f_list:
            self.misc["ZoneKwhPerDegFList"] = self.loaded.zone_kwh_per_deg_f_list
        else:
            self.misc["ZoneKwhPerDegFList"] = cfg.zone_kwh_per_deg_f_list
        self.misc["TotalStoreTanks"] = self.loaded.total_store_tanks
        # tmap is a generation-time input only: it populates the per-depth calibrated
        # derived channels (add_house0_derived_channels). The map is no longer stored in
        # the layout — the derived channels are the source of truth.
        self.misc["Strategy"] = self.loaded.strategy
        self.misc["FlowManifoldVariant"] = cfg.flow_manifold_variant
        self.misc["UseSiegLoop"] = cfg.use_sieg_loop
        self.misc["PrimaryFlowSource"] = cfg.primary_flow_source
        self.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.primary_scada),
                    Name=H0N.primary_scada,
                    ActorClass=ActorClass.PrimaryScada,
                    DisplayName=cfg.scada_display_name,
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.secondary_scada),
                    Name=H0N.secondary_scada,
                    ActorClass=ActorClass.SecondaryScada,
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
                    ShNodeId=self.make_node_id(H0N.ltn),
                    Name=H0N.ltn,
                    ActorClass=ActorClass.NoActor,
                    DisplayName="LeafTransactiveNode",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.leaf_ally),
                    Name=H0N.leaf_ally,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.leaf_ally}",
                    Handle=f"{H0N.ltn}.{H0N.leaf_ally}",
                    ActorClass=ActorClass.LeafAlly,
                    DisplayName="Leaf Ally",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.pico_cycler),
                    Name=H0N.pico_cycler,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.pico_cycler}",
                    Handle=f"auto.{H0N.pico_cycler}",
                    ActorClass=ActorClass.PicoCycler,
                    DisplayName="Pico Cycler - responsible for power cycling the 5VDC bus",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.derived_generator),
                    Name=H0N.derived_generator,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.derived_generator}",
                    ActorClass=ActorClass.DerivedGenerator,
                    DisplayName="Derived Generator",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.local_control),
                    Name=H0N.local_control,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.local_control}",
                    Handle=f"auto.{H0N.local_control}",
                    ActorClass=ActorClass.LocalControl,
                    DisplayName="LocalControl",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.local_control_normal),
                    Name=H0N.local_control_normal,
                    Handle=f"auto.{H0N.local_control}.{H0N.local_control_normal}",
                    ActorClass=ActorClass.NoActor,
                    DisplayName="LocalControl Normal",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.local_control_backup),
                    Name=H0N.local_control_backup,
                    Handle=f"auto.{H0N.local_control}.{H0N.local_control_backup}",
                    ActorClass=ActorClass.NoActor,
                    DisplayName="LocalControl Backup",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.local_control_scada_blind),
                    Name=H0N.local_control_scada_blind,
                    Handle=f"auto.{H0N.local_control}.{H0N.local_control_scada_blind}",
                    ActorClass=ActorClass.NoActor,
                    DisplayName="LocalControl Scada Blind",
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.make_node_id(H0N.hp_boss),
                    Name=H0N.hp_boss,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.hp_boss}",
                    Handle=f"auto.{H0N.local_control}.{H0N.local_control_normal}.{H0N.hp_boss}",
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
                    Handle=f"{H0N.auto}.{H0N.local_control}.{H0N.local_control_normal}.{H0N.sieg_loop}",
                    ActorClass=ActorClass.SiegLoop,
                    DisplayName="Siegenthaler Loop",
                ),
                ]
            )

            self.add_derived_channels(
                [DerivedChannelGt(
                Id = self.make_derived_channel_id(H0CN.hp_keep_seconds_x_10),
                Name = H0CN.hp_keep_seconds_x_10,
                CreatedByNodeName = H0N.sieg_loop,
                TerminalAssetAlias = self.terminal_asset_alias,
                Strategy = "Integrate relay motion",
                DisplayName = "Percent keep in the Siegenthaler loop",
                )
            ]
            )

        self.add_house0_derived_channels(tmap)

    def add_house0_derived_channels(self, tmap: TankTempCalibrationMap | None = None) -> None:
        if tmap is None:
            tmap = TankTempCalibrationMap(
                Buffer=TankTempCalibration(),
                Tank={
                    i: TankTempCalibration()
                    for i in range(1, self.loaded.total_store_tanks + 1)
                },
            )

        channels = [
            DerivedChannelGt(
                Id = self.make_derived_channel_id(H0CN.usable_energy),
                Name = H0CN.usable_energy,
                CreatedByNodeName = H0N.derived_generator,
                OutputUnit=GwUnit.WattHours,
                TerminalAssetAlias = self.terminal_asset_alias,
                Strategy = "system-model",
                EmissionMethod=EmissionMethod.Periodic,
                EmitPeriodS=60,
                InputChannelNames=[],
                Parameters={"EnergyModel": UsableEnergyLayered().model_dump()},
                DisplayName = "Usable Energy Wh",
                ),
            DerivedChannelGt(
                Id = self.make_derived_channel_id(H0CN.required_energy),
                Name = H0CN.required_energy,
                CreatedByNodeName = H0N.derived_generator,
                OutputUnit=GwUnit.WattHours,
                TerminalAssetAlias = self.terminal_asset_alias,
                Strategy = "system-model",
                EmissionMethod=EmissionMethod.Periodic,
                EmitPeriodS=60,
                InputChannelNames=[],
                Parameters={"EnergyModel": RequiredEnergyLayered().model_dump()},
                DisplayName = "Required Energy Wh",
                ),
            ]

        temp_mappings: list[tuple[str, str, TankTempCalibration, int]] = [
            (self.h0cn.buffer.depth1, self.h0cn.buffer.depth1_device, tmap.Buffer, 1),
            (self.h0cn.buffer.depth2, self.h0cn.buffer.depth2_device, tmap.Buffer, 2),
            (self.h0cn.buffer.depth3, self.h0cn.buffer.depth3_device, tmap.Buffer, 3),
        ]
        for tank_idx, tank in sorted(self.h0cn.tank.items()):
            cal = tmap.Tank[tank_idx]
            temp_mappings.extend(
                [
                    (tank.depth1, tank.depth1_device, cal, 1),
                    (tank.depth2, tank.depth2_device, cal, 2),
                    (tank.depth3, tank.depth3_device, cal, 3),
                ]
            )

        for cn, input_cn, cal, depth in temp_mappings:
            calibration = LinearOneDimensionalCalibration(
                M=getattr(cal, f"Depth{depth}M"),
                B=getattr(cal, f"Depth{depth}B"),
            )
            kwargs = {
                "Id": self.make_derived_channel_id(cn),
                "Name": cn,
                "CreatedByNodeName": H0N.derived_generator,
                "InputChannelNames": [input_cn],
                "OutputUnit": GwUnit.FahrenheitX100,
                "TerminalAssetAlias": self.terminal_asset_alias,
                "EmissionMethod": EmissionMethod.OnTrigger,
                "DisplayName": f"{cn.replace('-', ' ').title()} Effective Temperature",
            }
            if calibration.M == 1.0 and calibration.B == 0.0:
                kwargs["Strategy"] = "identity"
            else:
                kwargs["Strategy"] = "affine"
                kwargs["Parameters"] = {"Calibration": calibration.model_dump()}
            channels.append(DerivedChannelGt(**kwargs))

        self.add_derived_channels(channels)

    def add_stubs(self, 
                  cfg: Optional[StubConfig] = None,
                  *,
                  tmap: TankTempCalibrationMap | None = None):
        if cfg is None:
            cfg = StubConfig()
        self.add_stub_scadas(cfg, tmap=tmap)
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
        return self._nest_hydronic(d)

    @staticmethod
    def _nest_hydronic(d: dict) -> dict:
        """Fold the flat hydronic keys (which the builders write) into the typed
        nested gw.house0.hydronic 'Hydronic' block the layout carries."""
        if "ZoneList" not in d:
            return d
        critical = set(d.pop("CriticalZoneList", []))
        zone_list = d.pop("ZoneList")
        zone_kwh = d.pop("ZoneKwhPerDegFList", [])
        fmv = d.pop("FlowManifoldVariant", FlowManifoldVariant.House0)
        d["Hydronic"] = {
            "Zones": [
                {
                    "Name": name,
                    "Critical": name in critical,
                    "KwhPerDegF": kwh,
                    "TypeName": "gw1.hvac.zone",
                    "Version": "000",
                }
                for name, kwh in zip(zone_list, zone_kwh)
            ],
            "TotalStoreTanks": d.pop("TotalStoreTanks", 0),
            "UseSiegLoop": d.pop("UseSiegLoop", False),
            "SiegLoopPlumbed": fmv == FlowManifoldVariant.House0Sieg,
            "PrimaryFlowSource": d.pop("PrimaryFlowSource", "Measured"),
            "Strategy": d.pop("Strategy", "House0"),
            "TypeName": "gw.house0.hydronic",
            "Version": "000",
        }
        return d

    def write(self, path: str | Path) -> None:
        with Path(path).open("w") as f:
            f.write(json.dumps(self.dict(), sort_keys=True, indent=2))
