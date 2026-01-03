from typing import Dict, List, Literal
from pydantic import BaseModel
from gwsproto.enums import TelemetryName
from gwsproto.property_format import SpaceheatName
DEFAULT_ANALOG_READER = "analog-temp"


class ZoneNodes:
    """
    Spaceheat Node names associated to a zone:
    self.zone_name, self.stat, self.whitewire
    """
    def __init__(self, zone: str, idx: int) -> None:
        base = f"zone{idx + 1}-{zone}".lower()
        self.zone =  base
        self.stat = f"{base}-stat"
        self.whitewire=f"{base}-whitewire"

        # Required relays
        self.failsafe_relay = f"{base}-failsafe-relay"
        self.ops_relay = f"{base}-ops-relay"

    @property
    def required_relays(self) -> set[str]:
        "failsafe and ops relays"
        return {
            self.failsafe_relay,
            self.ops_relay,
        }

    @property
    def all(self) -> set[str]:
        """All required nodes this zone"""
        return {
            self.zone,
            self.stat,
            self.whitewire,
            self.failsafe_relay,
            self.ops_relay,
        }

    def __repr__(self) -> str:
        return f"Zone {self.zone} Spaceheat nodes: {sorted(self.all)}"

class BufferNodeNames:
    """
    Spaceheat Node names associated to the buffer"

    self.reader, self.depth1, self.depth2, self.depth3
    """
    def __init__(self) -> None:
        self.reader = "buffer"
        self.depth1 = "buffer-depth1"
        self.depth2 = "buffer-depth2"
        self.depth3 = "buffer-depth3"

    @property
    def depths(self) -> set[str]:
        return {
            self.depth1,
            self.depth2,
            self.depth3
        }

    def __repr__(self) -> str:
        return f"{self.reader} reads {sorted(self.depths)}"


class TankNodeNames: 
    """
    Spaceheat Node names associated to the tank

    self.reader, self.depth1, self.depth2, self.depth3
    Also self.all returns all nodes as a set
    """

    def __init__(self, idx: int) -> None:
        """ use idx between 1 and 6"""
        if idx > 6 or idx < 1:
            raise ValueError("Tank idx must be in between 1 and 6")
        self.reader = f"tank{idx}"
        self.depth1 = f"{self.reader}-depth1"
        self.depth2 = f"{self.reader}-depth2"
        self.depth3 = f"{self.reader}-depth3"

    @property
    def depths(self) -> set[str]:
        return {
            self.depth1,
            self.depth2,
            self.depth3
        }

    def __repr__(self) -> str:
        return f"{self.reader} reads {sorted(self.depths)}"

class House0RelayIdx:
    vdc: Literal[1] = 1
    tstat_common: Literal[2] = 2
    store_charge_disharge: Literal[3] = 3
    hp_failsafe: Literal[5] = 5
    hp_scada_ops: Literal[6] = 6
    thermistor_common: Literal[7] = 7
    aquastat_ctrl: Literal[8] = 8
    store_pump_failsafe: Literal[9] = 9
    boiler_scada_ops: Literal[10] = 10
    primary_pump_ops: Literal[11] = 11
    primary_pump_failsafe: Literal[12] = 12
    hp_loop_on_off: Literal[14] = 14
    hp_loop_keep_send: Literal[15] = 15
    # pattern: zone1 failsafe is 17, zone2 ops is 18 etc
    base_stat: Literal[17] = 17

class H0N:
    #system actor nodes
    primary_scada = "s"
    atn = "a"
    secondary_scada = "s2"
    atomic_ally = "aa"
    home_alone = "h"
    home_alone_normal = "n"
    home_alone_backup = "backup"
    home_alone_scada_blind = "scada-blind"
    primary_power_meter = "power-meter"
    admin = "admin" 
    auto = "auto"
    derived_generator = "derived-generator"
    pico_cycler = "pico-cycler"
    hp_boss = "hp-boss"

    # topology nodes
    # transactive nodes
    hp_odu = "hp-odu"
    hp_idu = "hp-idu"

    # pumps
    dist_pump = "dist-pump"
    primary_pump = "primary-pump"
    store_pump = "store-pump"

    # required pipe temperatures
    dist_swt = "dist-swt"
    dist_rwt = "dist-rwt"
    hp_lwt = "hp-lwt"
    hp_ewt = "hp-ewt"
    store_hot_pipe = "store-hot-pipe"
    store_cold_pipe = "store-cold-pipe"
    buffer_hot_pipe = "buffer-hot-pipe"
    buffer = BufferNodeNames()

    # relay nodes
    vdc_relay: Literal["relay1"] = "relay1"
    tstat_common_relay: Literal["relay2"] = "relay2"
    store_charge_discharge_relay: Literal["relay3"] = "relay3"
    hp_failsafe_relay: Literal["relay5"] = "relay5"
    hp_scada_ops_relay: Literal["relay6"] = "relay6"
    thermistor_common_relay: Literal["relay7"] = "relay7"
    aquastat_ctrl_relay: Literal["relay8"] = "relay8"
    store_pump_failsafe: Literal["relay9"] = "relay9"

    boiler_scada_ops: Literal["relay10"] = "relay10"
    primary_pump_scada_ops: Literal["relay11"] = "relay11"
    primary_pump_failsafe: Literal["relay12"] = "relay12"
    hp_loop_on_off: Literal["relay14"] = "relay14"
    hp_loop_keep_send: Literal["relay15"] = "relay15"

    # required flows
    dist_flow = "dist-flow"
    primary_flow = "primary-flow"
    store_flow = "store-flow"

    # zero ten output
    dist_010v = "dist-010v"
    primary_010v = "primary-010v"
    store_010v = "store-010v"

    hubitat = "hubitat"

    # instrumentation
    zero_ten_out_multiplexer = "zero-ten-multiplexer"
    analog_temp = "analog-temp"
    relay_multiplexer = "relay-multiplexer"
    dist_btu = "dist-btu"
    primary_btu = "primary-btu"
    store_btu = "store-btu"

    # Optional
    buffer_cold_pipe = "buffer-cold-pipe"
    sieg_flow = "sieg-flow"
    oat = "oat"
    sieg_cold = "sieg-cold"
    sieg_loop = "sieg-loop"


    def __init__(self, total_store_tanks: int, zone_list: List[str]) -> None:
        self.tank: Dict[int, TankNodeNames] = {}
        self.zone: Dict[str, ZoneNodes] = {}
        for i in range(total_store_tanks):
            self.tank[i + 1] = TankNodeNames(i + 1)
        for i in range(len(zone_list)):
            self.zone[zone_list[i]] = ZoneNodes(zone=zone_list[i], idx=i)



#-------------------------------------------------------------
# House 0 Channels
#--------------------------------------------------------------


class ChannelStub(BaseModel):
    """
    A ChannelStub defines the *semantic form* of a data channel that must exist
    in a House0Layout, independent of which instrument captures it.

    ChannelStubs are intended to be used by House0Layout to validate that a 
    layout contains the required channels with the correct meaning (units, and about-node),
    while allowing the capturing instrument (actor) to vary.

    Key design rules:
    - A ChannelStub does NOT specify CapturedByNodeName.
      Capture binding is a layout-level concern handled by the builder.
    - A ChannelStub DOES specify AboutNodeName, which encodes the semantic
      relationship of the measurement to the system topology.
    - A ChannelStub DOES specify TelemetryName (will transition to units)
    - ChannelStubs are stable across instrument substitutions; replacing
      hardware must not require changing ChannelStubs.
    """
    name: SpaceheatName
    about_node_name: SpaceheatName
    telemetry_name: TelemetryName
    in_power_metering: bool = False
    is_derived: bool = False
    
class ZoneChannelNames:
    def __init__(self, zone: str, idx: int) -> None:
        self.zone_name = f"zone{idx}-{zone}".lower()
        self.stat_name = f"{self.zone_name}-stat"
        self.temp = f"{self.zone_name}-temp"
        self.set = f"{self.zone_name}-set"
        self.state = f"{self.zone_name}-state"
        self.whitewire_pwr=f"{self.zone_name}-whitewire-pwr"

    @property
    def all(self) -> set[str]:
        """All required channels for this zone"""
        return {
            self.temp,
            self.set,
            self.state,
            self.whitewire_pwr,
        }

    def __repr__(self) -> str:
        return f"{self.zone_name} Channels: {sorted(self.all)}"

class BufferChannelNames:
    """
    Constructs expected SpaceheatName names for buffer tank's channels
    """
    def __init__(self) -> None:
        self.reader = "buffer"

        # effective (Used in the system, derived)
        self.depth1 = "buffer-depth1"
        self.depth2 = "buffer-depth2"
        self.depth3 = "buffer-depth3"

        # Device-level temperature reports
        self.depth1_device = "buffer-depth1-device"
        self.depth2_device = "buffer-depth2-device"
        self.depth3_device = "buffer-depth3-device"

        # Electrical measurement
        self.depth1_micro_v = "buffer-depth1-micro-v"
        self.depth2_micro_v = "buffer-depth2-micro-v"
        self.depth3_micro_v = "buffer-depth3-micro-v"


    @property
    def effective(self) -> set[str]:
        """Effective (derived) channels:buffer-depth1, buffer-depth2, buffer-depth3"""
        return {self.depth1, self.depth2, self.depth3}

    @property
    def device(self) -> set[str]:
        """Temperatures reported by device, e.g. TankModule3"""
        return {self.depth1_device, self.depth2_device, self.depth3_device}

    @property
    def electrical(self) -> set[str]:
        return {
            self.depth1_micro_v,
            self.depth2_micro_v,
            self.depth3_micro_v,
        }

    def __repr__(self) -> str:
        return (
            f"Buffer channels | effective={sorted(self.effective)} "
            f"| device={sorted(self.device)}"
            f"| electrical={sorted(self.electrical)}"
        )

class TankChannelNames:
    """
    Constructs expected SpaceheatName names for a store tank's channels
    """
    def __init__(self, idx: int) -> None:
        """ idx should be between 1 and 6"""
        if idx > 6 or idx < 1:
            raise ValueError("Tank idx must be in between 1 and 6")
        self.reader = f"tank{idx}"

        # effective (Used in the system, derived)
        self.depth1 = f"{self.reader}-depth1"
        self.depth2 = f"{self.reader}-depth2"
        self.depth3 = f"{self.reader}-depth3"

         # Device-level temperature reports
        self.depth1_device = f"{self.reader}-depth1-device"
        self.depth2_device = f"{self.reader}-depth2-device"
        self.depth3_device = f"{self.reader}-depth3-device"

        # Electrical measurement
        self.depth1_micro_v = f"{self.reader}-depth1-micro-v"
        self.depth2_micro_v = f"{self.reader}-depth2-micro-v"
        self.depth3_micro_v = f"{self.reader}-depth3-micro-v"

    @property
    def effective(self) -> set[str]:
        """Effective (derived) channels"""
        return {self.depth1, self.depth2, self.depth3}

    @property
    def device(self) -> set[str]:
        """Temperatures reported by device, e.g. TankModule3"""
        return {self.depth1_device, self.depth2_device, self.depth3_device}

    @property
    def electrical(self) -> set[str]:
        return {
            self.depth1_micro_v,
            self.depth2_micro_v,
            self.depth3_micro_v,
        }

    def __repr__(self) -> str:
        return (
            f"Buffer channels | effective={sorted(self.effective)} "
            f"| device={sorted(self.device)}"
            f"| electrical={sorted(self.electrical)}"
        )

class H0CN:
    # Power Channels
    hp_odu_pwr = f"{H0N.hp_odu}-pwr"
    hp_idu_pwr = f"{H0N.hp_idu}-pwr"
    dist_pump_pwr = f"{H0N.dist_pump}-pwr"
    primary_pump_pwr = f"{H0N.primary_pump}-pwr"
    store_pump_pwr = f"{H0N.store_pump}-pwr"

    # Temperature Channels
    dist_swt = H0N.dist_swt
    dist_rwt = H0N.dist_rwt
    hp_lwt = H0N.hp_lwt
    hp_ewt = H0N.hp_ewt
    store_hot_pipe = H0N.store_hot_pipe
    store_cold_pipe = H0N.store_cold_pipe
    buffer_hot_pipe = H0N.buffer_hot_pipe
    buffer_cold_pipe = H0N.buffer_cold_pipe
    oat = H0N.oat
    sieg_cold = H0N.sieg_cold
    buffer = BufferChannelNames()

    # Flow Channels
    dist_flow = H0N.dist_flow
    primary_flow = H0N.primary_flow
    store_flow = H0N.store_flow
    sieg_flow = H0N.sieg_flow
    dist_flow_hz = f"{H0N.dist_flow}-hz"
    primary_flow_hz = f"{H0N.primary_flow}-hz"
    store_flow_hz = f"{H0N.store_flow}-hz"

    # Synth Channels
    required_energy = "required-energy"
    usable_energy = "usable-energy"
    hp_keep_seconds_x_10 = "hp-keep-seconds-x-10"

    # relay state channels
    vdc_relay_state: Literal["vdc-relay1"] = "vdc-relay1"
    tstat_common_relay_state: Literal["tstat-common-relay2"] = "tstat-common-relay2"
    charge_discharge_relay_state: Literal["charge-discharge-relay3"] = "charge-discharge-relay3"
    hp_failsafe_relay_state = f"hp-failsafe-{H0N.hp_failsafe_relay}"
    thermistor_common_relay_state = f"thermistor-common-{H0N.thermistor_common_relay}"
    hp_scada_ops_relay_state = f"hp-scada-ops-{H0N.hp_scada_ops_relay}"
    aquastat_ctrl_relay_state = f"aquastat-ctrl-{H0N.aquastat_ctrl_relay}"
    store_pump_failsafe_relay_state = f"store-pump-failsafe-{H0N.store_pump_failsafe}"
    boiler_scada_ops_relay_state = f"boiler-scada_ops-{H0N.boiler_scada_ops}"
    primary_pump_scada_ops_relay_state = (
        f"primary-pump-scada-ops-{H0N.primary_pump_scada_ops}"
    )
    primary_pump_failsafe_relay_state = (
        f"primary-pump-failsafe-{H0N.primary_pump_failsafe}"
    )

    hp_loop_on_off_relay_state = f"hp-loop-on-off-{H0N.hp_loop_on_off}"
    hp_loop_keep_send_relay_state = f"hp-loop-keep-send-{H0N.hp_loop_keep_send}"

    # 010V output state (as declared by entity sending, not reading)
    dist_010v = "dist-010v"
    primary_010v = "primary-010v"
    store_010v = "store-010v"

    def __init__(self, total_store_tanks: int, zone_list: List[str]) -> None:
        self.tank: Dict[int, TankChannelNames] = {}
        self.zone: Dict[int, ZoneChannelNames] = {}
        for i in range(total_store_tanks):
            self.tank[i + 1] = TankChannelNames(i + 1)
        for i in range(len(zone_list)):
            self.zone[i + 1] = ZoneChannelNames(zone=zone_list[i], idx=i + 1)

    def channel_stubs(self) -> Dict[str, ChannelStub]:
        """
        Intended to verify relationship between channels and nodes.

        Not enforced yet and may be out of date
        """

        d = {
            self.hp_odu_pwr: ChannelStub(
                name=self.hp_odu_pwr,
                about_node_name=H0N.hp_odu,
                telemetry_name=TelemetryName.PowerW,
                in_power_metering=True,
            ),
            self.hp_idu_pwr: ChannelStub(
                name=self.hp_idu_pwr,
                about_node_name=H0N.hp_idu,
                telemetry_name=TelemetryName.PowerW,
                in_power_metering=True,
            ),
            self.dist_pump_pwr: ChannelStub(
                name=self.dist_pump_pwr,
                about_node_name=H0N.dist_pump,
                telemetry_name=TelemetryName.PowerW,
            ),
            self.primary_pump_pwr: ChannelStub(
                name=self.primary_pump_pwr,
                about_node_name=H0N.primary_pump,
                telemetry_name=TelemetryName.PowerW,
            ),
            self.store_pump_pwr: ChannelStub(
                name=self.store_pump_pwr,
                about_node_name=H0N.store_pump,
                telemetry_name=TelemetryName.PowerW,
            ),
            self.dist_swt: ChannelStub(
                name=self.dist_swt,
                about_node_name=H0N.dist_swt,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.dist_rwt: ChannelStub(
                name=self.dist_rwt,
                about_node_name=H0N.dist_rwt,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.hp_lwt: ChannelStub(
                name=self.hp_lwt,
                about_node_name=H0N.hp_lwt,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.hp_ewt: ChannelStub(
                name=self.hp_ewt,
                about_node_name=H0N.hp_ewt,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.store_hot_pipe: ChannelStub(
                name=self.store_hot_pipe,
                about_node_name=H0N.store_hot_pipe,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.store_cold_pipe: ChannelStub(
                name=self.store_cold_pipe,
                about_node_name=H0N.store_cold_pipe,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer_hot_pipe: ChannelStub(
                name=self.buffer_hot_pipe,
                about_node_name=H0N.buffer_hot_pipe,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer_cold_pipe: ChannelStub(
                name=self.buffer_cold_pipe,
                about_node_name=H0N.buffer_cold_pipe,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.oat: ChannelStub(
                name=self.oat,
                about_node_name=H0N.oat,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.dist_flow: ChannelStub(
                name=self.dist_flow,
                about_node_name=H0N.dist_flow,
                telemetry_name=TelemetryName.GpmTimes100,
            ),
            self.primary_flow: ChannelStub(
                name=self.primary_flow,
                about_node_name=H0N.primary_flow,
                telemetry_name=TelemetryName.GpmTimes100,
            ),
            self.store_flow: ChannelStub(
                name=self.store_flow,
                about_node_name=H0N.store_flow,
                telemetry_name=TelemetryName.GpmTimes100,
            ),
            self.buffer.depth1: ChannelStub(
                name=self.buffer.depth1,
                about_node_name=H0N.buffer.depth1,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
                is_derived=True,
            ),
            self.buffer.depth2: ChannelStub(
                name=self.buffer.depth2,
                about_node_name=H0N.buffer.depth2,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
                is_derived=True,
            ),
            self.buffer.depth3: ChannelStub(
                name=self.buffer.depth3,
                about_node_name=H0N.buffer.depth3,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
                is_derived=True,
            ),
            self.buffer.depth1: ChannelStub(
                name=self.buffer.depth1_raw,
                about_node_name=H0N.buffer.depth1,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer.depth2: ChannelStub(
                name=self.buffer.depth2_raw,
                about_node_name=H0N.buffer.depth2,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer.depth3: ChannelStub(
                name=self.buffer.depth3_raw,
                about_node_name=H0N.buffer.depth3,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            ),
        }
        for i in self.tank:
            d[self.tank[i].depth1] = ChannelStub(
                name=self.tank[i].depth1_device,
                about_node_name=self.tank[i].depth1,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
                is_derived=True,
            )
            d[self.tank[i].depth2] = ChannelStub(
                name=self.tank[i].depth2,
                about_node_name=self.tank[i].depth2,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
                is_derived=True,
            )
            d[self.tank[i].depth3] = ChannelStub(
                name=self.tank[i].depth3,
                about_node_name=self.tank[i].depth3,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
                is_derived=True,
            )
            d[self.tank[i].depth1] = ChannelStub(
                name=self.tank[i].depth1_device,
                about_node_name=self.tank[i].depth1,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            )
            d[self.tank[i].depth2] = ChannelStub(
                name=self.tank[i].depth2_device,
                about_node_name=self.tank[i].depth2,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            )
            d[self.tank[i].depth3] = ChannelStub(
                name=self.tank[i].depth3_device,
                about_node_name=self.tank[i].depth3,
                telemetry_name=TelemetryName.WaterTempCTimes1000,
            )

        for i in self.zone:
            d[self.zone[i].temp] = ChannelStub(
                    name=self.zone[i].temp,
                    about_node_name=self.zone[i].zone_name,
                    telemetry_name=TelemetryName.AirTempFTimes1000,
                )
            d[self.zone[i].set] = ChannelStub(
                    name=self.zone[i].set,
                    about_node_name=self.zone[i].stat_name,
                    telemetry_name=TelemetryName.AirTempFTimes1000,
                )
            d[self.zone[i].state] = ChannelStub(
                    name=self.zone[i].state,
                    about_node_name=self.zone[i].stat_name,
                    telemetry_name=TelemetryName.ThermostatState,
                )
            d[self.zone[i].whitewire_pwr] = ChannelStub(
                    name=self.zone[i].whitewire_pwr,
                    about_node_name=f"{self.zone[i]}-whitewire",
                    telemetry_name=TelemetryName.PowerW,
                )
            
        return d
