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

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from gwsproto.enums import (
    ActorClass,
    AquastatControl,
    ChangeAquastatControl,
    ChangeHeatcallSource,
    ChangeHeatPumpControl,
    ChangeKeepSend,
    ChangePrimaryPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    EmissionMethod,
    GpmFromHzMethod,
    DeviceType,
    Quantity,
    Unit,
    HzCalcMethod,
    HeatcallSource,
    HeatPumpControl,
    HpLoopKeepSend,
    PrimaryPumpControl,
    RelayClosedOrOpen,
    RelayWiringConfig,
    StoreFlowRelay,
    TelemetryName,
    ThermistorDataMethod,
    Unit,
)
from gwproto.type_helpers import WebServerGt
from gwsproto.named_types import (
    Ads111xBasedComponentGt,
    Ads111xBasedDeviceTypeGt,
    AdsChannelConfig,
    ChannelConfig,
    DataChannelGt,
    DerivedChannelGt,
    DfrComponentGt,
    DfrConfig,
    EgaugeRegisterConfig,
    ElectricMeterChannelConfig,
    ElectricMeterComponentGt,
    ElectricMeterDeviceTypeGt,
    GNodeGt,
    Gw1HvacZone,
    House0Hydronic,
    House0Layout as House0Sema,
    HubitatComponentGt,
    HubitatPollerComponentGt,
    HubitatPollerGt,
    I2cMultichannelDtRelayComponentGt,
    MakerAPIAttributeGt,
    PicoFlowModuleComponentGt,
    PicoTankModuleComponentGt,
    RelayActorConfig,
    SimPicoTankModuleComponentGt,
    SpaceheatNodeGt,
    WebServerComponentGt,
)
from gwsproto.named_types.hubitat_gt import HubitatGt


# New-convention channel-name transform: drop the trailing relay-index suffix
# (old `vdc-relay1` -> new `vdc-relay`). The base is already unique. This is the
# one systematic House0 channel rename in the names/ migration; used both to emit
# new names and to map a frozen (old-named) fixture's UUIDs onto the new names.
_RELAY_IDX_SUFFIX = re.compile(r"(-relay)\d+$")


def strip_relay_idx(name: str) -> str:
    return _RELAY_IDX_SUFFIX.sub(r"\1", name)


# Relay wiring/event/state bundles (mirrors layout_gen/relay.py).
_RELAY_KINDS = {
    "nc": dict(  # normally-closed simple relay: close=de-energize
        wiring=RelayWiringConfig.NormallyClosed, event=ChangeRelayState, state=RelayClosedOrOpen,
        deenergizing=ChangeRelayState.CloseRelay, energizing=ChangeRelayState.OpenRelay,
        deenergized=RelayClosedOrOpen.RelayClosed, energized=RelayClosedOrOpen.RelayOpen,
    ),
    "no_close": dict(  # normally-open simple relay: close=energize
        wiring=RelayWiringConfig.NormallyOpen, event=ChangeRelayState, state=RelayClosedOrOpen,
        deenergizing=ChangeRelayState.OpenRelay, energizing=ChangeRelayState.CloseRelay,
        deenergized=RelayClosedOrOpen.RelayOpen, energized=RelayClosedOrOpen.RelayClosed,
    ),
    "store_flow": dict(
        wiring=RelayWiringConfig.NormallyOpen, event=ChangeStoreFlowRelay, state=StoreFlowRelay,
        deenergizing=ChangeStoreFlowRelay.DischargeStore, energizing=ChangeStoreFlowRelay.ChargeStore,
        deenergized=StoreFlowRelay.DischargingStore, energized=StoreFlowRelay.ChargingStore,
    ),
    "hp_control": dict(
        wiring=RelayWiringConfig.DoubleThrow, event=ChangeHeatPumpControl, state=HeatPumpControl,
        deenergizing=ChangeHeatPumpControl.SwitchToTankAquastat, energizing=ChangeHeatPumpControl.SwitchToScada,
        deenergized=HeatPumpControl.BufferTankAquastat, energized=HeatPumpControl.Scada,
    ),
    "aquastat": dict(
        wiring=RelayWiringConfig.DoubleThrow, event=ChangeAquastatControl, state=AquastatControl,
        deenergizing=ChangeAquastatControl.SwitchToBoiler, energizing=ChangeAquastatControl.SwitchToScada,
        deenergized=AquastatControl.Boiler, energized=AquastatControl.Scada,
    ),
    "primary_pump_control": dict(
        wiring=RelayWiringConfig.DoubleThrow, event=ChangePrimaryPumpControl, state=PrimaryPumpControl,
        deenergizing=ChangePrimaryPumpControl.SwitchToHeatPump, energizing=ChangePrimaryPumpControl.SwitchToScada,
        deenergized=PrimaryPumpControl.HeatPump, energized=PrimaryPumpControl.Scada,
    ),
    "keep_send": dict(
        wiring=RelayWiringConfig.DoubleThrow, event=ChangeKeepSend, state=HpLoopKeepSend,
        deenergizing=ChangeKeepSend.ChangeToKeepLess, energizing=ChangeKeepSend.ChangeToKeepMore,
        deenergized=HpLoopKeepSend.SendMore, energized=HpLoopKeepSend.SendLess,
    ),
    "heatcall": dict(
        wiring=RelayWiringConfig.DoubleThrow, event=ChangeHeatcallSource, state=HeatcallSource,
        deenergizing=ChangeHeatcallSource.SwitchToWallThermostat, energizing=ChangeHeatcallSource.SwitchToScada,
        deenergized=HeatcallSource.WallThermostat, energized=HeatcallSource.Scada,
    ),
}

# The invariant non-zone relays, in layout order (note 12 before 11):
# (krida_idx, House0ChannelNames state attr, node DisplayName, channel DisplayName, kind)
_NONZONE_RELAYS = [
    (1, "vdc_relay_state", "5VDC Relay", "5V DC Bus Relay State", "nc"),
    (2, "tstat_common_relay_state", "TStat Common Relay", "TStat Common Relay State", "nc"),
    (3, "charge_discharge_relay_state", "Store Charge/Discharge Relay", "Charge/Discharge Relay State", "store_flow"),
    (5, "hp_failsafe_relay_state", "Hp Failsafe Relay", "Hp Failsafe Relay State", "hp_control"),
    (6, "hp_scada_ops_relay_state", "Hp Scada Ops Relay", "Hp Scada Ops Relay State", "nc"),
    (7, "thermistor_common_relay_state", "Thermistor Common Relay", "Thermistor Common Relay State", "nc"),
    (8, "aquastat_ctrl_relay_state", "Aquastat Ctrl Relay", "Aquastat Control Relay State", "aquastat"),
    (9, "store_pump_failsafe_relay_state", "Store Pump Failsafe", "Store Pump Failsafe Relay State", "no_close"),
    (12, "primary_pump_failsafe_relay_state", "Primary Pump Failsafe", "Primary Pump Failsafe Relay State", "primary_pump_control"),
    (11, "primary_pump_scada_ops_relay_state", "Primary Pump SCADA Ops", "Primary Pump SCADA Ops Relay State", "no_close"),
    (14, "hp_loop_on_off_relay_state", "Hp Loop Valve Active/Dormant Relay", "Hp Loop On Off Relay State", "nc"),
    (15, "hp_loop_keep_send_relay_state", "Hp Loop Valve SendMore/SendLess Relay", "Hp Loop Keep/Send Relay State", "keep_send"),
]

from gwsproto.names.core.channel_names import CoreChannelNames as CoreC
from gwsproto.names.core.node_names import CoreNodeNames as Core
from gwsproto.names.house0.channel_names import House0ChannelNames
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import (
    HydronicSpaceheatChannelNames as HydC,
    HydronicSpaceheatZoneChannelNames,
)
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as Hyd,
    HydronicSpaceheatZoneNodeNames,
)
from layout_gen.layout_db import LayoutIDMap


# --------------------------------------------------------------------------- #
# Config — the four config axes plus identity/zone/tank inputs. Mirrors the dc
# StubConfig + the Hydronic axes, but is the sema gen's own first-class input.
# --------------------------------------------------------------------------- #
@dataclass
class PwrChannelSpec:
    """One metered power channel on the (eGauge) electric meter: the channel, its
    about-node, the modbus register address, and the about-node's nameplate."""
    channel: str
    about_node: str
    address: int
    async_capture_delta: int
    nameplate_w: int | None
    in_power_metering: bool


@dataclass
class AdsChannelSpec:
    """One pipe-temp on the ADS analog-temp board: the channel (== about-node),
    its terminal-block index, and its telemetry (water vs air temp)."""
    channel: str
    terminal_block_idx: int
    telemetry: str = "WaterTempCTimes1000"


@dataclass
class TankSpec:
    """A real pico tank module (buffer or tankN, in reader order): its pico HwUid
    and the affine depth-calibration (depths 1 & 3 affine M·x+B, depth 2 identity)."""
    hwuid: str
    affine_m: float
    affine_b: int


@dataclass
class FlowSpec:
    """One Reed flow meter at a position (dist/primary/store). The hardware ids
    are per-home; the rest of the pico config is constant across the fleet."""
    position: str
    hwuid: str
    serial: str


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
    # peripheral inputs (per-zone thermostat device ids align to zone_list)
    web_server_host: str = "0.0.0.0"
    web_server_port: int = 8080
    relay_i2c_address_list: Sequence[int] = (0x20, 0x21)
    tank_kind: str = "sim"  # "sim" (GridworksSimSensor) or "real" (GridworksTankModule3)
    tanks: Sequence[TankSpec] = ()  # buffer first, then tank1..N (real tanks only)
    hubitat_host: str = "192.168.0.1"
    hubitat_maker_api_id: int = 1
    hubitat_access_token: str = ""
    hubitat_mac: str = ""
    zone_device_ids: Sequence[int] = ()
    dfr_initial_volts_times_100: Sequence[int] = (20, 40, 0)  # dist / primary / store
    # power meter: "sim" (GridworksSimPowerMeter) or "egauge" (real EgaugePowerMeter)
    power_meter_kind: str = "sim"
    egauge_modbus_host: str = ""
    egauge_modbus_port: int = 502
    egauge_hwuid: str = ""
    power_meter_channels: Sequence[PwrChannelSpec] = ()
    # ADS analog-temp board (absent on the sim stub)
    ads_hwuid: str = ""
    ads_open_voltage_by_ads: Sequence[float] = ()
    ads_channels: Sequence[AdsChannelSpec] = ()
    # Reed flow meters (in layout/component order; empty on the sim stub)
    flow_meters: Sequence[FlowSpec] = ()

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
        # UUID preservation across the new-convention rename: a frozen fixture is
        # keyed by OLD channel names (e.g. `vdc-relay1`); index its ids by the
        # NEW (stripped) name so an emitted new name inherits the existing UUID.
        self._channel_id_by_new = {
            strip_relay_idx(name): cid
            for name, cid in self.ids.channels_by_name.items()
        }

    # -- stable-id helpers (mirror LayoutDb.make_*_id) ---------------------- #
    def node_id(self, name: str) -> str:
        return self.ids.nodes_by_name.get(name, str(uuid.uuid4()))

    def channel_id(self, name: str) -> str:
        return (
            self.ids.channels_by_name.get(name)
            or self._channel_id_by_new.get(name)
            or str(uuid.uuid4())
        )

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

    def emit_hydronic(self) -> House0Hydronic:
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
        return House0Hydronic(
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
            node(Core.primary_scada, ActorClass.PrimaryScada, self.config.scada_display_name),
            node(Core.secondary_scada, ActorClass.SecondaryScada, "Secondary Scada"),
            node(Core.admin, ActorClass.NoActor, "Local Admin", Handle="admin"),
            node(Core.auto, ActorClass.NoActor, "Auto - FSM for dispatch contract", Handle="auto"),
            node(Core.ltn, ActorClass.NoActor, "LeafTransactiveNode"),
            node(
                Core.leaf_ally, ActorClass.LeafAlly, "Leaf Ally",
                ActorHierarchyName=f"{Core.primary_scada}.{Core.leaf_ally}", Handle="ltn.la",
            ),
            node(
                Hyd.pico_cycler, ActorClass.PicoCycler,
                "Pico Cycler - responsible for power cycling the 5VDC bus",
                ActorHierarchyName=f"{Core.primary_scada}.{Hyd.pico_cycler}",
                Handle="auto.pico-cycler",
            ),
            node(
                Core.derived_generator, ActorClass.DerivedGenerator, "Derived Generator",
                ActorHierarchyName=f"{Core.primary_scada}.{Core.derived_generator}",
            ),
            node(
                Core.local_control, ActorClass.LocalControl, "LocalControl",
                ActorHierarchyName=f"{Core.primary_scada}.{Core.local_control}", Handle="auto.lc",
            ),
            node(Hyd.local_control_normal, ActorClass.NoActor, "LocalControl Normal", Handle="auto.lc.n"),
            node(Hyd.local_control_backup, ActorClass.NoActor, "LocalControl Backup", Handle="auto.lc.backup"),
            node(
                Hyd.local_control_scada_blind, ActorClass.NoActor, "LocalControl Scada Blind",
                Handle="auto.lc.scada-blind",
            ),
            node(
                Hyd.hp_boss, ActorClass.HpBoss, "HeatpumpBoss",
                ActorHierarchyName=f"{Core.primary_scada}.{Hyd.hp_boss}", Handle="auto.lc.n.hp-boss",
            ),
        ]

    def emit_power_meter(self) -> None:
        if self.config.power_meter_kind == "egauge":
            self.emit_egauge_power_meter()
        else:
            self.emit_sim_power_meter()

    def emit_egauge_power_meter(self) -> None:
        """Real eGauge meter: EgaugePowerMeter device-type, the electric-meter
        component (modbus + per-channel register config), the power-meter node,
        and each metered channel's about-node + uppercase-named *-pwr DataChannel."""
        n = self.config.n
        alias = "EGauge Power Meter"
        cid = self.component_id(alias)

        self.device_types.append(
            ElectricMeterDeviceTypeGt(
                DeviceType=DeviceType.EgaugePowerMeter, DisplayName="EGauge 4030",
                TelemetryNameList=[TelemetryName.PowerW], MinPollPeriodMs=1000,
            )
        )
        self.components.append(
            ElectricMeterComponentGt(
                ComponentId=cid, DeviceType=DeviceType.EgaugePowerMeter, DisplayName=alias,
                ModbusHost=self.config.egauge_modbus_host, ModbusPort=self.config.egauge_modbus_port,
                HwUid=self.config.egauge_hwuid,
                ConfigList=[
                    ElectricMeterChannelConfig(
                        ChannelName=s.channel, PollPeriodMs=1000, CapturePeriodS=300,
                        AsyncCapture=True, AsyncCaptureDelta=s.async_capture_delta, Exponent=0, Unit=Unit.W,
                        EgaugeRegisterConfig=EgaugeRegisterConfig(
                            Address=s.address, Name=s.about_node, Denominator=1,
                            Description="change in value", Type="f32", Unit="W",
                        ),
                    )
                    for s in self.config.power_meter_channels
                ],
            )
        )
        self.sh_nodes.append(
            SpaceheatNodeGt(
                ShNodeId=self.node_id(Core.asset_power_meter), Name=Core.asset_power_meter,
                ActorClass=ActorClass.PowerMeter, ActorHierarchyName=f"{Core.primary_scada}.{Core.asset_power_meter}",
                DisplayName="Primary Power Meter", ComponentId=cid,
            )
        )
        for s in self.config.power_meter_channels:
            kw = {"InPowerMetering": s.in_power_metering}
            if s.nameplate_w is not None:
                kw["NameplatePowerW"] = s.nameplate_w
            self.sh_nodes.append(
                SpaceheatNodeGt(
                    ShNodeId=self.node_id(s.about_node), Name=s.about_node, ActorClass=ActorClass.NoActor,
                    DisplayName=s.about_node.replace("-", " ").title(), **kw,
                )
            )
        for s in self.config.power_meter_channels:
            self.data_channels.append(
                DataChannelGt(
                    Name=s.channel, DisplayName=s.channel.replace("-", " ").upper(),
                    AboutNodeName=s.about_node, CapturedByNodeName=Core.asset_power_meter,
                    TelemetryName=TelemetryName.PowerW, Quantity=Quantity.Power,
                    InPowerMetering=s.in_power_metering, Id=self.channel_id(s.channel),
                    TerminalAssetAlias=self.terminal_asset_alias,
                )
            )

    def emit_sim_power_meter(self) -> None:
        """Sim power meter: device-type record, component, its 3 nodes
        (hp-odu, hp-idu, store-pump), and the three *-pwr DataChannels."""
        n = self.config.n
        cn = self.config.cn
        alias = "Power Meter for Simulated Test system"

        self.device_types.append(
            ElectricMeterDeviceTypeGt(
                DeviceType=DeviceType.GridworksSimPowerMeter,
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
                DeviceType=DeviceType.GridworksSimPowerMeter,
                DisplayName=alias,
                ConfigList=[
                    em_cfg(HydC.hp_odu_pwr, 200),
                    em_cfg(HydC.hp_idu_pwr, 200),
                    em_cfg(HydC.store_pump_pwr, 5),
                ],
            )
        )

        self.sh_nodes += [
            SpaceheatNodeGt(
                ShNodeId=self.node_id(Core.asset_power_meter),
                Name=Core.asset_power_meter,
                ActorClass=ActorClass.PowerMeter,
                ActorHierarchyName=f"{Core.primary_scada}.{Core.asset_power_meter}",
                DisplayName="Main Power Meter Little Orange House Test System",
                ComponentId=self.component_id(alias),
            ),
            SpaceheatNodeGt(
                ShNodeId=self.node_id(Hyd.hp_odu), Name=Hyd.hp_odu, ActorClass=ActorClass.NoActor,
                DisplayName="HP ODU", NameplatePowerW=6000, InPowerMetering=True,
            ),
            SpaceheatNodeGt(
                ShNodeId=self.node_id(Hyd.hp_idu), Name=Hyd.hp_idu, ActorClass=ActorClass.NoActor,
                DisplayName="HP IDU", NameplatePowerW=4000, InPowerMetering=True,
            ),
            SpaceheatNodeGt(
                ShNodeId=self.node_id(Hyd.store_pump), Name=Hyd.store_pump,
                ActorClass=ActorClass.NoActor, DisplayName="Store Pump",
            ),
        ]

        def pwr_channel(name: str, about: str, in_metering: bool) -> DataChannelGt:
            return DataChannelGt(
                Name=name,
                DisplayName=" ".join(p.upper() for p in name.split("-")),
                AboutNodeName=about,
                CapturedByNodeName=Core.asset_power_meter,
                TelemetryName=TelemetryName.PowerW,
                Quantity=Quantity.Power,
                InPowerMetering=in_metering,
                Id=self.channel_id(name),
                TerminalAssetAlias=self.terminal_asset_alias,
            )

        self.data_channels += [
            pwr_channel(HydC.hp_odu_pwr, Hyd.hp_odu, True),
            pwr_channel(HydC.hp_idu_pwr, Hyd.hp_idu, True),
            pwr_channel(HydC.store_pump_pwr, Hyd.store_pump, False),
        ]

    def emit_relays(self) -> None:
        """The i2c Krida relay bank: the multichannel component, the
        relay-multiplexer node, the per-relay nodes, and the relay-state
        DataChannels. Relay-state channels use the NEW convention (no trailing
        relay-index); UUIDs carry over from the frozen fixture via channel_id."""
        n = self.config.n
        cn = self.config.cn
        alias = "i2c krida relay boards"
        rid = self.component_id(alias)
        mux = n.relay_multiplexer

        cfgs: list[RelayActorConfig] = []
        nodes: list[SpaceheatNodeGt] = []
        chans: list[DataChannelGt] = []

        def add_relay(idx, channel, node_display, chan_display, kind) -> None:
            node = f"relay{idx}"
            k = _RELAY_KINDS[kind]
            cfgs.append(
                RelayActorConfig(
                    ChannelName=channel,
                    RelayIdx=idx,
                    ActorName=node,
                    PollPeriodMs=200,
                    CapturePeriodS=300,
                    WiringConfig=k["wiring"],
                    EventType=k["event"].enum_name(),
                    StateType=k["state"].enum_name(),
                    DeEnergizingEvent=k["deenergizing"],
                    EnergizingEvent=k["energizing"],
                    DeEnergizedState=k["deenergized"],
                    EnergizedState=k["energized"],
                    AsyncCapture=True,
                    AsyncCaptureDelta=1,
                    Exponent=0,
                    Unit=Unit.Unitless,
                )
            )
            handle = (
                f"auto.{Hyd.pico_cycler}.{node}" if idx == 1
                else f"auto.{Core.local_control}.{Hyd.local_control_normal}.{node}"
            )
            nodes.append(
                SpaceheatNodeGt(
                    ShNodeId=self.node_id(node), Name=node,
                    ActorHierarchyName=f"{Core.primary_scada}.{node}", Handle=handle,
                    ActorClass=ActorClass.Relay, DisplayName=node_display, ComponentId=rid,
                )
            )
            chans.append(
                DataChannelGt(
                    Name=channel, DisplayName=chan_display,
                    AboutNodeName=node, CapturedByNodeName=mux,
                    TelemetryName=TelemetryName.RelayState, Quantity=Quantity.Unitless,
                    Id=self.channel_id(channel), TerminalAssetAlias=self.terminal_asset_alias,
                )
            )

        for idx, state_attr, node_disp, chan_disp, kind in _NONZONE_RELAYS:
            # most relay-state channels are House0-specific (krida board); `vdc-relay`
            # is a hydronic-shared name, so fall back to the hydronic class.
            channel = getattr(cn, state_attr, None) or getattr(HydC, state_attr)
            add_relay(idx, channel, node_disp, chan_disp, kind)

        # Per-zone failsafe + scada-ops relays (krida idx 17/18, 19/20, …).
        for i, zone in enumerate(self.config.zone_list):
            zc = HydronicSpaceheatZoneChannelNames(zone, i + 1)  # relay-state is a hydronic-shared name
            label = zone.capitalize()
            add_relay(
                17 + 2 * i, zc.failsafe_relay_state,
                f"{label} Zone {i + 1} Failsf", f"{label} Zone {i + 1} Failsf Relay State", "heatcall",
            )
            add_relay(
                18 + 2 * i, zc.ops_relay_state,
                f"{label} Zone Scada Ops", f"{label} Zone {i + 1} Scada Ops Relay State", "no_close",
            )

        self.components.append(
            I2cMultichannelDtRelayComponentGt(
                ComponentId=rid,
                DeviceType=DeviceType.KridaDoubleRelayBoard16,
                DisplayName=alias,
                ConfigList=cfgs,
                I2cBus="default",
                I2cAddressList=list(self.config.relay_i2c_address_list),
            )
        )
        self.sh_nodes.append(
            SpaceheatNodeGt(
                ShNodeId=self.node_id(mux), Name=mux,
                ActorHierarchyName=f"{Core.primary_scada}.{mux}",
                ActorClass=ActorClass.I2cRelayMultiplexer,
                DisplayName="I2c Relay Multiplexer", ComponentId=rid,
            )
        )
        self.sh_nodes += nodes
        self.data_channels += chans

    def emit_web_server(self) -> None:
        self.components.append(
            WebServerComponentGt(
                ComponentId=self.component_id("Web Server default"),
                DeviceType=DeviceType.AbstractWebServer,
                DisplayName="Web Server default",
                WebServer=WebServerGt(Host=self.config.web_server_host, Port=self.config.web_server_port),
                ConfigList=[],
            )
        )

    def emit_thermostat(self) -> None:
        """Hubitat hub component + per-zone Honeywell thermostat poller, the
        hubitat node, and per-zone stat/zone nodes + temp/set/state channels."""
        n = self.config.n
        hub_alias = f"Hubitat {self.config.hubitat_mac[-8:]}"
        hub_id = self.component_id(hub_alias)
        hub = HubitatGt(
            Host=self.config.hubitat_host,
            MakerApiId=self.config.hubitat_maker_api_id,
            AccessToken=self.config.hubitat_access_token,
            MacAddress=self.config.hubitat_mac,
        )
        self.components.append(
            HubitatComponentGt(
                ComponentId=hub_id, DeviceType=DeviceType.HubitatC7Hub,
                DisplayName=hub_alias, Hubitat=hub,
                HwUid=self.config.hubitat_mac[-8:].replace(":", "").lower(), ConfigList=[],
            )
        )

        device_ids = list(self.config.zone_device_ids)
        zone_nodes: list[SpaceheatNodeGt] = []
        zone_chans: list[DataChannelGt] = []
        for i, zone in enumerate(self.config.zone_list):
            idx = i + 1
            # hydronic-shared zone names come from the hydronic classes; only the
            # House0-specific / retiring names are built here.
            zn = HydronicSpaceheatZoneNodeNames(zone, idx)
            zc = HydronicSpaceheatZoneChannelNames(zone, idx)
            base = zc.base
            label = zone.capitalize()              # "living-rm" -> "Living-rm" (node/relay displays)
            chan_label = base.replace("-", " ").title()  # -> "Zone1 Living Rm" (channel displays)
            stat, znode = zn.stat, zn.zone
            temp, setp = zc.temp, zc.set
            state = f"{base}-state"                # sick Hubitat channel; not in the names hierarchy
            device_id = device_ids[i] if i < len(device_ids) else idx
            poller_alias = f"Thermostat {idx} for {zone}"
            poller_id = self.component_id(poller_alias)

            def attr(name, channel, node, telemetry, unit, interpret) -> MakerAPIAttributeGt:
                return MakerAPIAttributeGt(
                    AttributeName=name, ChannelName=channel, NodeName=node,
                    TelemetryName=telemetry, Unit=unit, Exponent=3,
                    InterpretAsNumber=interpret, Enabled=True, WebPollEnabled=True,
                    WebListenEnabled=True, ReportMissing=True, ReportParseError=True,
                )

            self.components.append(
                HubitatPollerComponentGt(
                    ComponentId=poller_id, DeviceType=DeviceType.HoneywellT6Thermostat,
                    DisplayName=poller_alias,
                    ConfigList=[
                        ChannelConfig(ChannelName=temp, PollPeriodMs=5000, CapturePeriodS=300,
                                      AsyncCapture=True, AsyncCaptureDelta=1, Exponent=3, Unit=Unit.Fahrenheit),
                        ChannelConfig(ChannelName=setp, PollPeriodMs=5000, CapturePeriodS=300,
                                      AsyncCapture=False, Exponent=3, Unit=Unit.Fahrenheit),
                        ChannelConfig(ChannelName=state, PollPeriodMs=5000, CapturePeriodS=300,
                                      AsyncCapture=True, AsyncCaptureDelta=1, Exponent=0, Unit=Unit.ThermostatStateEnum),
                    ],
                    Poller=HubitatPollerGt(
                        HubitatComponentId=hub_id, DeviceId=device_id,
                        Attributes=[
                            attr("temperature", temp, znode, TelemetryName.AirTempFTimes1000, Unit.Fahrenheit, True),
                            attr("heatingSetpoint", setp, stat, TelemetryName.AirTempFTimes1000, Unit.Fahrenheit, True),
                            attr("thermostatOperatingState", state, znode, TelemetryName.ThermostatState, Unit.Unitless, False),
                        ],
                        Enabled=True, WebListenEnabled=True, PollPeriodSeconds=300.0,
                    ),
                )
            )

            zone_nodes += [
                SpaceheatNodeGt(
                    ShNodeId=self.node_id(stat), Name=stat, ActorClass=ActorClass.HoneywellThermostat,
                    ActorHierarchyName=f"{Core.secondary_scada}.{stat}",
                    DisplayName=f"Zone {idx} {label} Thermostat", ComponentId=poller_id,
                ),
                SpaceheatNodeGt(
                    ShNodeId=self.node_id(znode), Name=znode, ActorClass=ActorClass.NoActor,
                    DisplayName=f"Zone {idx} {label}",
                ),
            ]
            zone_chans += [
                DataChannelGt(Name=temp, DisplayName=f"{chan_label} Temp", AboutNodeName=znode,
                              CapturedByNodeName=stat, TelemetryName=TelemetryName.AirTempFTimes1000,
                              Quantity=Quantity.Temperature, Id=self.channel_id(temp),
                              TerminalAssetAlias=self.terminal_asset_alias),
                DataChannelGt(Name=setp, DisplayName=f"{chan_label} Set", AboutNodeName=stat,
                              CapturedByNodeName=stat, TelemetryName=TelemetryName.AirTempFTimes1000,
                              Quantity=Quantity.Temperature, Id=self.channel_id(setp),
                              TerminalAssetAlias=self.terminal_asset_alias),
                DataChannelGt(Name=state, DisplayName=f"{chan_label} State", AboutNodeName=stat,
                              CapturedByNodeName=stat, TelemetryName=TelemetryName.ThermostatState,
                              Quantity=Quantity.Unitless, Id=self.channel_id(state),
                              TerminalAssetAlias=self.terminal_asset_alias),
            ]

        self.sh_nodes.append(
            SpaceheatNodeGt(
                ShNodeId=self.node_id(n.hubitat), Name=n.hubitat, ActorClass=ActorClass.Hubitat,
                ActorHierarchyName=f"{Core.primary_scada}.{n.hubitat}", DisplayName=hub_alias, ComponentId=hub_id,
            )
        )
        self.sh_nodes += zone_nodes
        self.data_channels += zone_chans

    def emit_tanks(self) -> None:
        """The buffer + each storage tank as a pico tank module (sim or real):
        component (6 channel configs), the reader node, three depth nodes, and the
        device/micro-v DataChannels (all devices, then all micro-v, per tank)."""
        readers = ["buffer"] + [f"tank{i}" for i in range(1, self.config.total_store_tanks + 1)]
        real = self.config.tank_kind == "real"
        for ri, reader in enumerate(readers):
            disp = reader.capitalize()
            device = [ChannelConfig(ChannelName=f"{reader}-depth{d}-device", CapturePeriodS=60,
                                    AsyncCapture=True, AsyncCaptureDelta=2000, Exponent=3, Unit=Unit.Celcius)
                      for d in (1, 2, 3)]
            microv = [ChannelConfig(ChannelName=f"{reader}-depth{d}-micro-v", CapturePeriodS=60,
                                    AsyncCapture=True, AsyncCaptureDelta=2000, Exponent=6, Unit=Unit.VoltsRms)
                      for d in (1, 2, 3)]
            # real tank: all devices then all micro-v; sim tank: interleaved per depth
            if real:
                cfgs = device + microv
            else:
                cfgs = [c for pair in zip(device, microv) for c in pair]
            common = dict(
                ConfigList=cfgs, AsyncCaptureDeltaMicroVolts=2000, Enabled=True, NumSampleAverages=30,
                Samples=1000, SendMicroVolts=True, SerialNumber="NA", TempCalcMethod="SimpleBeta",
                ThermistorBeta=3977,
            )
            if real:
                spec = self.config.tanks[ri]
                alias = f"{reader} PicoTankModule"
                cid = self.component_id(alias)
                self.components.append(
                    PicoTankModuleComponentGt(
                        ComponentId=cid, DeviceType=DeviceType.GridworksTankModule3, DisplayName=alias,
                        PicoHwUid=spec.hwuid, **common,
                    )
                )
                reader_display = f"{disp} Tank"
            else:
                alias = disp
                cid = self.component_id(alias)
                self.components.append(
                    SimPicoTankModuleComponentGt(
                        ComponentId=cid, DeviceType=DeviceType.GridworksSimSensor, DisplayName=disp,
                        PicoHwUid=f"sim-{reader}-pico", SimulatesTypeName="pico.tank.module.component.gt",
                        SimulatesVersion="012", **common,
                    )
                )
                reader_display = f"{disp} SIMULATED ApiTankModule actor"
            self.sh_nodes.append(
                SpaceheatNodeGt(
                    ShNodeId=self.node_id(reader), Name=reader, ActorClass=ActorClass.ApiTankModule,
                    ActorHierarchyName=f"{Core.primary_scada}.{reader}",
                    DisplayName=reader_display, ComponentId=cid,
                )
            )
            for depth in (1, 2, 3):
                dn = f"{reader}-depth{depth}"
                self.sh_nodes.append(
                    SpaceheatNodeGt(ShNodeId=self.node_id(dn), Name=dn, ActorClass=ActorClass.NoActor, DisplayName=dn)
                )
            for kind, telemetry, quantity, suffix, unit_word in (
                ("Device Temp", TelemetryName.WaterTempCTimes1000, Quantity.Temperature, "device", None),
                ("MicroVolts", TelemetryName.MicroVolts, Quantity.Voltage, "micro-v", None),
            ):
                for depth in (1, 2, 3):
                    name = f"{reader}-depth{depth}-{suffix}"
                    self.data_channels.append(
                        DataChannelGt(
                            Name=name, DisplayName=f"{disp} Depth {depth} {kind}",
                            AboutNodeName=f"{reader}-depth{depth}", CapturedByNodeName=reader,
                            TelemetryName=telemetry, Quantity=quantity,
                            Id=self.channel_id(name), TerminalAssetAlias=self.terminal_asset_alias,
                        )
                    )

    def emit_dfr(self) -> None:
        """The DFRobot dual 0-10V outputer: component, the multiplexer node, the
        three 010V outputer nodes, and their DataChannels."""
        n = self.config.n
        alias = "DFRobot 010V output X 2"
        cid = self.component_id(alias)
        outs = [("dist-010v", "Dist", Hyd.dist_010v), ("primary-010v", "Primary", Hyd.primary_010v),
                ("store-010v", "Store", Hyd.store_010v)]
        volts = list(self.config.dfr_initial_volts_times_100)
        self.components.append(
            DfrComponentGt(
                ComponentId=cid, DeviceType=DeviceType.DfrobotDualAnalogOut, DisplayName=alias,
                I2cAddressList=[0x5E, 0x5F],
                ConfigList=[
                    DfrConfig(ChannelName=chan, CapturePeriodS=300, AsyncCapture=True, AsyncCaptureDelta=1,
                              Exponent=1, Unit=Unit.VoltsRms, OutputIdx=i + 1, InitialVoltsTimes100=volts[i])
                    for i, (chan, _, _) in enumerate(outs)
                ],
            )
        )
        self.sh_nodes.append(
            SpaceheatNodeGt(
                ShNodeId=self.node_id(n.zero_ten_out_multiplexer), Name=n.zero_ten_out_multiplexer,
                ActorClass=ActorClass.I2cZeroTenMultiplexer,
                ActorHierarchyName=f"{Core.primary_scada}.{n.zero_ten_out_multiplexer}",
                DisplayName="I2c Zero Ten Out Multiplexer", ComponentId=cid,
            )
        )
        for chan, label, node in outs:
            self.sh_nodes.append(
                SpaceheatNodeGt(
                    ShNodeId=self.node_id(node), Name=node, ActorClass=ActorClass.ZeroTenOutputer,
                    ActorHierarchyName=f"{Core.primary_scada}.{node}", Handle=f"auto.{node}",
                    DisplayName=f"{label} DFR",
                )
            )
        for chan, label, node in outs:
            self.data_channels.append(
                DataChannelGt(
                    Name=chan, DisplayName=f"{label} 010V", AboutNodeName=node,
                    CapturedByNodeName=n.zero_ten_out_multiplexer, TelemetryName=TelemetryName.VoltsTimesTen,
                    Quantity=Quantity.Voltage, Id=self.channel_id(chan),
                    TerminalAssetAlias=self.terminal_asset_alias,
                )
            )

    def emit_ads(self) -> None:
        """The ADS111x analog-temp board (TSnap): device-type, component, the
        analog-temp node, and each pipe-temp's about-node + DataChannel."""
        if not self.config.ads_channels:
            return
        n = self.config.n
        alias = f"Multipurpose Temp Sensor <{self.config.ads_hwuid}>"
        cid = self.component_id(alias)

        self.device_types.append(
            Ads111xBasedDeviceTypeGt(
                DeviceType=DeviceType.GridworksTsnap1ScadaBoard,
                DisplayName="GridWorks TSnap1.0 as 12-channel analog temp sensor",
                MinPollPeriodMs=200, TotalTerminalBlocks=12,
                TelemetryNameList=[TelemetryName.WaterTempCTimes1000, TelemetryName.AirTempCTimes1000],
                AdsI2cAddressList=[0x4B, 0x49, 0x48],
            )
        )
        self.components.append(
            Ads111xBasedComponentGt(
                ComponentId=cid, DeviceType=DeviceType.GridworksTsnap1ScadaBoard, DisplayName=alias,
                HwUid=self.config.ads_hwuid, OpenVoltageByAds=list(self.config.ads_open_voltage_by_ads),
                ConfigList=[
                    AdsChannelConfig(
                        ChannelName=s.channel, AsyncCapture=True, AsyncCaptureDelta=500, CapturePeriodS=300,
                        DataProcessingMethod=ThermistorDataMethod.BetaWithExponentialAveraging, Exponent=3,
                        TerminalBlockIdx=s.terminal_block_idx, ThermistorDeviceType=DeviceType.TewaThermistor,
                        Unit=Unit.Celcius,
                    )
                    for s in self.config.ads_channels
                ],
            )
        )
        self.sh_nodes.append(
            SpaceheatNodeGt(
                ShNodeId=self.node_id(n.analog_temp), Name=n.analog_temp,
                ActorClass=ActorClass.MultipurposeSensor,
                ActorHierarchyName=f"{Core.secondary_scada}.{n.analog_temp}",
                DisplayName="ANALOG TEMP", ComponentId=cid,
            )
        )
        for s in self.config.ads_channels:
            self.sh_nodes.append(
                SpaceheatNodeGt(ShNodeId=self.node_id(s.channel), Name=s.channel,
                                ActorClass=ActorClass.NoActor, DisplayName=s.channel.replace("-", " ").upper())
            )
        for s in self.config.ads_channels:
            self.data_channels.append(
                DataChannelGt(
                    Name=s.channel, DisplayName=s.channel.replace("-", " ").upper(),
                    AboutNodeName=s.channel, CapturedByNodeName=n.analog_temp,
                    TelemetryName=TelemetryName(s.telemetry), Quantity=Quantity.Temperature,
                    Id=self.channel_id(s.channel), TerminalAssetAlias=self.terminal_asset_alias,
                )
            )

    def emit_flow(self) -> None:
        """Reed flow meters: per position a `pico.flow.module` component, the
        ApiFlowModule node, and the `*-flow` (Gpm) + `*-flow-hz` (MicroHz) channels."""
        n = self.config.n
        for f in self.config.flow_meters:
            node = f"{f.position}-flow"
            label = node.replace("-", " ").title()
            cid = self.component_id(f"{label} ReedFlowModule")
            self.components.append(
                PicoFlowModuleComponentGt(
                    ComponentId=cid, DeviceType=DeviceType.GridworksPicoFlowReed,
                    DisplayName=f"{label} ReedFlowModule", FlowNodeName=node,
                    HwUid=f.hwuid, SerialNumber=f.serial, Enabled=True,
                    FlowMeterType=DeviceType.EkmFlowMeter,
                    HzCalcMethod=HzCalcMethod.BasicExpWeightedAvg,
                    GpmFromHzMethod=GpmFromHzMethod.Constant, ConstantGallonsPerTick=0.0748,
                    SendHz=True, SendGallons=False, SendTickLists=False, NoFlowMs=5000,
                    PublishAnyTicklistAfterS=10, AsyncCaptureThresholdGpmTimes100=5,
                    PublishTicklistLength=10, ExpAlpha=0.5,
                    ConfigList=[
                        ChannelConfig(ChannelName=node, CapturePeriodS=300, AsyncCapture=True,
                                      Exponent=2, Unit=Unit.Gpm),
                        ChannelConfig(ChannelName=f"{node}-hz", CapturePeriodS=300, AsyncCapture=True,
                                      Exponent=6, Unit=Unit.VoltsRms),
                    ],
                )
            )
            self.sh_nodes.append(
                SpaceheatNodeGt(
                    ShNodeId=self.node_id(node), Name=node, ActorClass=ActorClass.ApiFlowModule,
                    ActorHierarchyName=f"{Core.primary_scada}.{node}", DisplayName=label, ComponentId=cid,
                )
            )
            self.data_channels += [
                DataChannelGt(Name=node, DisplayName=f"{label} Gpm X 100", AboutNodeName=node,
                              CapturedByNodeName=node, TelemetryName=TelemetryName.GpmTimes100,
                              Quantity=Quantity.FlowRate, Id=self.channel_id(node),
                              TerminalAssetAlias=self.terminal_asset_alias),
                DataChannelGt(Name=f"{node}-hz", DisplayName=f"{label} MicroHz", AboutNodeName=node,
                              CapturedByNodeName=node, TelemetryName=TelemetryName.MicroHz,
                              Quantity=Quantity.Frequency, Id=self.channel_id(f"{node}-hz"),
                              TerminalAssetAlias=self.terminal_asset_alias),
            ]

    def emit_derived_channels(self) -> None:
        """System-model energy channels + per-depth tank/buffer calibration."""
        n = self.config.n

        def energy(name, display, model_type) -> DerivedChannelGt:
            return DerivedChannelGt(
                Name=name, DisplayName=display, CreatedByNodeName=Core.derived_generator,
                EmissionMethod=EmissionMethod.Periodic, EmitPeriodS=60, InputChannelNames=[],
                OutputQuantity=Quantity.Energy, OutputUnit=Unit.WattHours, Strategy="system-model",
                Parameters={"EnergyModel": {"TypeName": model_type, "Version": "000"}},
                Id=self.derived_channel_id(name), TerminalAssetAlias=self.terminal_asset_alias,
            )

        self.derived_channels += [
            energy("usable-energy", "Usable Energy Wh", "gw0.usable.energy.layered"),
            energy("required-energy", "Required Energy Wh", "gw0.required.energy.layered"),
        ]
        readers = ["buffer"] + [f"tank{i}" for i in range(1, self.config.total_store_tanks + 1)]
        tanks = list(self.config.tanks)
        for ri, reader in enumerate(readers):
            # real tanks calibrate depths 1 & 3 affine (M·x + B), depth 2 identity;
            # sim tanks are identity throughout.
            spec = tanks[ri] if (self.config.tank_kind == "real" and ri < len(tanks)) else None
            for depth in (1, 2, 3):
                name = f"{reader}-depth{depth}"
                affine = spec is not None and depth in (1, 3)
                params = None
                if affine:
                    params = {"Calibration": {
                        "M": spec.affine_m, "B": spec.affine_b,
                        "TypeName": "linear.one.dimensional.calibration", "Version": "001",
                    }}
                self.derived_channels.append(
                    DerivedChannelGt(
                        Name=name, DisplayName=f"{reader.capitalize()} Depth{depth} Effective Temperature",
                        CreatedByNodeName=Core.derived_generator, EmissionMethod=EmissionMethod.OnTrigger,
                        InputChannelNames=[f"{name}-device"], OutputQuantity=Quantity.Temperature,
                        OutputUnit=Unit.FahrenheitX100, Strategy="affine" if affine else "identity",
                        Parameters=params,
                        Id=self.derived_channel_id(name), TerminalAssetAlias=self.terminal_asset_alias,
                    )
                )

    # -- assembly ----------------------------------------------------------- #
    def build(self) -> House0Sema:
        self.emit_gnodes()
        hydronic = self.emit_hydronic()
        self.emit_system_actor_nodes()
        self.emit_power_meter()
        self.emit_web_server()
        self.emit_thermostat()
        self.emit_relays()
        self.emit_tanks()
        self.emit_dfr()
        self.emit_flow()
        self.emit_ads()
        self.emit_derived_channels()
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
