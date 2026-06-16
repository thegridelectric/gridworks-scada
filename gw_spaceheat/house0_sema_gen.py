"""Sema-native House0 layout generator (hardware-layout-pass-one, Task a).

Build a `gw.house0.layout` Sema object DIRECTLY from a config, without going
through the dc dataclasses. This is the parallel to the old dc-based gen
(`layout_gen/`), and its purpose is twofold:

1. validate `sema_gen(config) == dc_to_sema(load(reference_layout))` for the
   fleet shapes (the reference is a frozen on-disk layout JSON);
2. be the **fixture factory** for the layout-axiom counterexample tests — only a
   sema-native gen can emit a layout that *violates* a `gw.house0.layout` axiom,
   because the dc loader's Python guards raise before the sema codec ever runs.

Stable IDs come from the same mechanism the old gen uses: IDs are keyed by name
out of a reference layout (`LayoutIDMap`), so a name present in the reference
gets its exact ID and the equality holds.

STATUS: skeleton. Emits GNodes, Hydronic, the invariant system-actor nodes, and
the power-meter component/nodes/channels. The remaining builders (relays, tanks,
dfr, thermostat zone, derived channels) are driven in by the diff harness
`house0_sema_gen_check.py` — generate, observe the gap, close it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from gwsproto.enums import ActorClass
from gwsproto.enums import Gw1DeviceType
from gwsproto.enums import GwQuantity
from gwsproto.enums import TelemetryName
from gwsproto.enums import Unit
from gwsproto.named_types import (
    DataChannelGt,
    DerivedChannelGt,
    ElectricMeterChannelConfig,
    ElectricMeterComponentGt,
    ElectricMeterDeviceTypeGt,
    GNodeGt,
    Gw1HvacZone,
    GwHouse0Hydronic,
    House0Layout as House0Sema,
    SpaceheatNodeGt,
)

from gwsproto.names.house0.channel_names import House0ChannelNames
from gwsproto.names.house0.node_names import House0NodeNames
from layout_gen.layout_db import LayoutIDMap


# --------------------------------------------------------------------------- #
# Config — the four config axes plus identity/zone/tank inputs. Mirrors the dc
# StubConfig + the Hydronic axes, but is the sema gen's own first-class input.
# --------------------------------------------------------------------------- #
@dataclass
class House0SemaGenConfig:
    scada_display_name: str
    zone_list: Sequence[str]
    critical_zone_list: Sequence[str]
    zone_kwh_per_deg_f_list: Sequence[float]
    total_store_tanks: int
    strategy: str = "House0"
    use_sieg_loop: bool = False
    sieg_loop_plumbed: bool = False
    primary_flow_source: str = "Measured"

    @property
    def n(self) -> House0NodeNames:
        return House0NodeNames(self.total_store_tanks, list(self.zone_list))

    @property
    def cn(self) -> House0ChannelNames:
        return House0ChannelNames(self.total_store_tanks, list(self.zone_list))


class House0SemaGen:
    """Accumulates the sema layout collections, then assembles a House0Sema."""

    def __init__(self, config: House0SemaGenConfig, reference: Path):
        self.config = config
        self.ids = LayoutIDMap.from_path(reference)
        self.gnodes: list[GNodeGt] = []
        self.sh_nodes: list[SpaceheatNodeGt] = []
        self.data_channels: list[DataChannelGt] = []
        self.derived_channels: list[DerivedChannelGt] = []
        self.components: list = []
        self.device_types: list = []
        self.terminal_asset_alias = (
            self.ids.gnodes.get("MyTerminalAssetGNode", {}).get("Alias", "")
        )

    # -- stable-id helpers (mirror LayoutDb.make_*_id) ---------------------- #
    def node_id(self, name: str) -> str:
        return self.ids.nodes_by_name.get(name, str(uuid.uuid4()))

    def channel_id(self, name: str) -> str:
        return self.ids.channels_by_name.get(name, str(uuid.uuid4()))

    def derived_channel_id(self, name: str) -> str:
        return self.ids.derived_channels_by_name.get(name, str(uuid.uuid4()))

    def component_id(self, alias: str) -> str:
        return self.ids.components_by_alias.get(alias, str(uuid.uuid4()))

    # -- emitters ----------------------------------------------------------- #
    def emit_gnodes(self) -> None:
        for key in ("MyLeafTransactiveNodeGNode", "MyTerminalAssetGNode", "MyScadaGNode"):
            gn = self.ids.gnodes.get(key)
            if gn is not None:
                self.gnodes.append(GNodeGt.model_validate(gn))

    def emit_hydronic(self) -> GwHouse0Hydronic:
        critical = set(self.config.critical_zone_list)
        kwh = list(self.config.zone_kwh_per_deg_f_list)
        zones = [
            Gw1HvacZone(
                Name=name,
                Critical=name in critical,
                KwhPerDegF=kwh[i] if i < len(kwh) else 1,
            )
            for i, name in enumerate(self.config.zone_list)
        ]
        return GwHouse0Hydronic(
            Zones=zones,
            TotalStoreTanks=self.config.total_store_tanks,
            UseSiegLoop=self.config.use_sieg_loop,
            SiegLoopPlumbed=self.config.sieg_loop_plumbed,
            PrimaryFlowSource=self.config.primary_flow_source,
            Strategy=self.config.strategy,
        )

    def emit_system_actor_nodes(self) -> None:
        """The 14 invariant system-actor nodes (House0 skeleton)."""
        n = self.config.n

        def node(name: str, actor: ActorClass, display: str, **kw) -> SpaceheatNodeGt:
            return SpaceheatNodeGt(
                ShNodeId=self.node_id(name),
                Name=name,
                ActorClass=actor,
                DisplayName=display,
                **kw,
            )

        self.sh_nodes += [
            node(n.primary_scada, ActorClass.PrimaryScada, self.config.scada_display_name),
            node(n.secondary_scada, ActorClass.SecondaryScada, "Secondary Scada"),
            node(n.admin, ActorClass.NoActor, "Local Admin", Handle="admin"),
            node(n.auto, ActorClass.NoActor, "Auto - FSM for dispatch contract", Handle="auto"),
            node(n.ltn, ActorClass.NoActor, "LeafTransactiveNode"),
            node(
                n.leaf_ally, ActorClass.LeafAlly, "Leaf Ally",
                ActorHierarchyName=f"{n.primary_scada}.{n.leaf_ally}", Handle="ltn.la",
            ),
            node(
                n.pico_cycler, ActorClass.PicoCycler,
                "Pico Cycler - responsible for power cycling the 5VDC bus",
                ActorHierarchyName=f"{n.primary_scada}.{n.pico_cycler}",
                Handle="auto.pico-cycler",
            ),
            node(
                n.derived_generator, ActorClass.DerivedGenerator, "Derived Generator",
                ActorHierarchyName=f"{n.primary_scada}.{n.derived_generator}",
            ),
            node(
                n.local_control, ActorClass.LocalControl, "LocalControl",
                ActorHierarchyName=f"{n.primary_scada}.{n.local_control}", Handle="auto.lc",
            ),
            node(n.local_control_normal, ActorClass.NoActor, "LocalControl Normal", Handle="auto.lc.n"),
            node(n.local_control_backup, ActorClass.NoActor, "LocalControl Backup", Handle="auto.lc.backup"),
            node(
                n.local_control_scada_blind, ActorClass.NoActor, "LocalControl Scada Blind",
                Handle="auto.lc.scada-blind",
            ),
            node(
                n.hp_boss, ActorClass.HpBoss, "HeatpumpBoss",
                ActorHierarchyName=f"{n.primary_scada}.{n.hp_boss}", Handle="auto.lc.n.hp-boss",
            ),
        ]

    def emit_power_meter(self) -> None:
        """eGauge/sim power meter: device-type record, component, its 3 nodes
        (hp-odu, hp-idu, store-pump), and the three *-pwr DataChannels."""
        n = self.config.n
        cn = self.config.cn
        alias = "Power Meter for Simulated Test system"

        self.device_types.append(
            ElectricMeterDeviceTypeGt(
                DeviceType=Gw1DeviceType.GridworksSimPowerMeter,
                DisplayName="Gridworks Pm1 Simulated Power Meter",
                TelemetryNameList=[TelemetryName.PowerW],
                MinPollPeriodMs=1000,
            )
        )

        def em_cfg(channel: str, delta: int) -> ElectricMeterChannelConfig:
            return ElectricMeterChannelConfig(
                ChannelName=channel,
                PollPeriodMs=1000,
                CapturePeriodS=300,
                AsyncCapture=True,
                AsyncCaptureDelta=delta,
                Exponent=0,
                Unit=Unit.W,
            )

        self.components.append(
            ElectricMeterComponentGt(
                ComponentId=self.component_id(alias),
                DeviceType=Gw1DeviceType.GridworksSimPowerMeter,
                DisplayName=alias,
                ConfigList=[
                    em_cfg(cn.hp_odu_pwr, 200),
                    em_cfg(cn.hp_idu_pwr, 200),
                    em_cfg(cn.store_pump_pwr, 5),
                ],
            )
        )

        self.sh_nodes += [
            SpaceheatNodeGt(
                ShNodeId=self.node_id(n.asset_power_meter),
                Name=n.asset_power_meter,
                ActorClass=ActorClass.PowerMeter,
                ActorHierarchyName=f"{n.primary_scada}.{n.asset_power_meter}",
                DisplayName="Main Power Meter Little Orange House Test System",
                ComponentId=self.component_id(alias),
            ),
            SpaceheatNodeGt(
                ShNodeId=self.node_id(n.hp_odu), Name=n.hp_odu, ActorClass=ActorClass.NoActor,
                DisplayName="HP ODU", NameplatePowerW=6000, InPowerMetering=True,
            ),
            SpaceheatNodeGt(
                ShNodeId=self.node_id(n.hp_idu), Name=n.hp_idu, ActorClass=ActorClass.NoActor,
                DisplayName="HP IDU", NameplatePowerW=4000, InPowerMetering=True,
            ),
            SpaceheatNodeGt(
                ShNodeId=self.node_id(n.store_pump), Name=n.store_pump,
                ActorClass=ActorClass.NoActor, DisplayName="Store Pump",
            ),
        ]

        def pwr_channel(name: str, about: str, in_metering: bool) -> DataChannelGt:
            return DataChannelGt(
                Name=name,
                DisplayName=" ".join(p.upper() for p in name.split("-")),
                AboutNodeName=about,
                CapturedByNodeName=n.asset_power_meter,
                TelemetryName=TelemetryName.PowerW,
                Quantity=GwQuantity.Power,
                InPowerMetering=in_metering,
                Id=self.channel_id(name),
                TerminalAssetAlias=self.terminal_asset_alias,
            )

        self.data_channels += [
            pwr_channel(cn.hp_odu_pwr, n.hp_odu, True),
            pwr_channel(cn.hp_idu_pwr, n.hp_idu, True),
            pwr_channel(cn.store_pump_pwr, n.store_pump, False),
        ]

    # -- assembly ----------------------------------------------------------- #
    def build(self) -> House0Sema:
        self.emit_gnodes()
        hydronic = self.emit_hydronic()
        self.emit_system_actor_nodes()
        self.emit_power_meter()
        return House0Sema(
            GNodes=self.gnodes or None,
            ShNodes=self.sh_nodes,
            DataChannels=self.data_channels,
            DerivedChannels=self.derived_channels,
            Components=self.components,
            DeviceTypes=self.device_types,
            Hydronic=hydronic,
        )


def sema_gen(config: House0SemaGenConfig, reference: Path) -> House0Sema:
    return House0SemaGen(config, reference).build()
