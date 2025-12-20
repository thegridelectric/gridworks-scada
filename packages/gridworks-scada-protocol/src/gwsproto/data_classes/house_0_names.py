from typing import ClassVar, Dict, List, Literal
from pydantic import BaseModel
from gwproto.enums import TelemetryName
from gwproto.property_format import SpaceheatName
DEFAULT_ANALOG_READER = "analog-temp"


class ZoneNodes:
    """
    Spaceheat Node names associated to a zone:
    self.zone_name, self.stat, self.whitewire
    """
    def __init__(self, zone: str, idx: int) -> None:
        self.zone_name =  f"zone{idx + 1}-{zone}".lower()
        self.stat = f"{self.zone_name}-stat"
        self.whitewire=f"{self.zone_name}-whitewire"

    @property
    def all(self) -> set[str]:
        """All required nodes this zone"""
        return {
            self.zone_name,
            self.stat,
            self.whitewire,
        }

    def __repr__(self) -> str:
        return f"Zone {self.zone_name} Spaceheat nodes: {sorted(self.all)}"

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
    def all(self) -> set[str]:
        """All required buffer Spaceheat nodes"""
        return {
            self.reader,
            self.depth1,
            self.depth2,
            self.depth3
        }

    def __repr__(self) -> str:
        return f"{self.reader} Spaceheat nodes: {sorted(self.all)}"


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
    def all(self) -> set[str]:
        """All required buffer Spaceheat nodes"""
        return {
            self.reader,
            self.depth1,
            self.depth2,
            self.depth3
        }

    def __repr__(self) -> str:
        return f"{self.reader} reads {sorted(self.all)}"

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
    # core actors
    atn = "a"
    atomic_ally = "aa"
    primary_scada = "s"
    secondary_scada = "s2"
    home_alone = "h"
    home_alone_normal = "n"
    home_alone_backup = "backup"
    home_alone_scada_blind = "scada-blind"
    primary_power_meter = "power-meter"
    admin = "admin"  # used when starter scripts take control
    auto = "auto"  # Finite State Machine responsible for homealone <-> atn transition
    analog_temp = "analog-temp"
    relay_multiplexer = "relay-multiplexer"
    synth_generator = "synth-generator"
    zero_ten_out_multiplexer = "dfr-multiplexer"
    hp_boss = "hp-boss"
    sieg_loop = "sieg-loop"

    # core power-metered nodes
    hp_odu = "hp-odu"
    hp_idu = "hp-idu"
    dist_pump = "dist-pump"
    primary_pump = "primary-pump"
    store_pump = "store-pump"

    # core temperatures
    dist_swt = "dist-swt"
    dist_rwt = "dist-rwt"
    hp_lwt = "hp-lwt"
    hp_ewt = "hp-ewt"
    buffer_hot_pipe = "buffer-hot-pipe"
    buffer_cold_pipe = "buffer-cold-pipe"
    store_hot_pipe = "store-hot-pipe"
    store_cold_pipe = "store-cold-pipe"
    oat = "oat"
    sieg_cold = "sieg-cold"
    buffer = BufferNodeNames()

    # core flow-metered nodes
    dist_flow = "dist-flow"
    primary_flow = "primary-flow"
    store_flow = "store-flow"
    sieg_flow = "sieg-flow"

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

    # zero ten output
    dist_010v = "dist-010v"
    primary_010v = "primary-010v"
    store_010v = "store-010v"
    hubitat = "hubitat"

    # finite state machines
    pico_cycler = "pico-cycler"

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
    Name: SpaceheatName
    AboutNodeName: SpaceheatName
    TelemetryName: TelemetryName
    InPowerMetering: bool = False


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

    can call self.depth1, self.depth2 and self.depth3 or self.all for all 3 as set
    """
    def __init__(self) -> None:
        self.reader = "buffer"
        self.depth1 = "buffer-depth1"
        self.depth2 = "buffer-depth2"
        self.depth3 = "buffer-depth3"

    @property
    def all(self) -> set[str]:
        """All required channels: buffer-depth1, buffer-depth2, buffer-depth3"""
        return {
            self.depth1,
            self.depth2,
            self.depth3,
        }

    def __repr__(self) -> str:
        return f"buffer channels: {sorted(self.all)}"

class TankChannelNames:
    """
    Constructs expected SpaceheatName names for a store tank's channels

    can call self.depth1, self.depth2 and self.depth3 or self.all for all 3 as set
    """
    def __init__(self, idx: int) -> None:
        """ idx should be between 1 and 6"""
        if idx > 6 or idx < 1:
            raise ValueError("Tank idx must be in between 1 and 6")
        self.reader = f"tank{idx}"
        self.depth1 = f"{self.reader}-depth1"
        self.depth2 = f"{self.reader}-depth2"
        self.depth3 = f"{self.reader}-depth3"
    
    @property
    def all(self) -> set[str]:
        """All required channels for this tank: tank{i}-depth1, tank{i}-depth2, tank{i}-depth3"""
        return {
            self.depth1, 
            self.depth2,
            self.depth3,
        }

    def __repr__(self) -> str:
        return f"Tank {self.reader} channels: {sorted(self.all)}"

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
                Name=self.hp_odu_pwr,
                AboutNodeName=H0N.hp_odu,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=True,
            ),
            self.hp_idu_pwr: ChannelStub(
                Name=self.hp_idu_pwr,
                AboutNodeName=H0N.hp_idu,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=True,
            ),
            self.dist_pump_pwr: ChannelStub(
                Name=self.dist_pump_pwr,
                AboutNodeName=H0N.dist_pump,
                TelemetryName=TelemetryName.PowerW,
            ),
            self.primary_pump_pwr: ChannelStub(
                Name=self.primary_pump_pwr,
                AboutNodeName=H0N.primary_pump,
                TelemetryName=TelemetryName.PowerW,
            ),
            self.store_pump_pwr: ChannelStub(
                Name=self.store_pump_pwr,
                AboutNodeName=H0N.store_pump,
                TelemetryName=TelemetryName.PowerW,
            ),
            self.dist_swt: ChannelStub(
                Name=self.dist_swt,
                AboutNodeName=H0N.dist_swt,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.dist_rwt: ChannelStub(
                Name=self.dist_rwt,
                AboutNodeName=H0N.dist_rwt,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.hp_lwt: ChannelStub(
                Name=self.hp_lwt,
                AboutNodeName=H0N.hp_lwt,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.hp_ewt: ChannelStub(
                Name=self.hp_ewt,
                AboutNodeName=H0N.hp_ewt,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.store_hot_pipe: ChannelStub(
                Name=self.store_hot_pipe,
                AboutNodeName=H0N.store_hot_pipe,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.store_cold_pipe: ChannelStub(
                Name=self.store_cold_pipe,
                AboutNodeName=H0N.store_cold_pipe,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer_hot_pipe: ChannelStub(
                Name=self.buffer_hot_pipe,
                AboutNodeName=H0N.buffer_hot_pipe,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer_cold_pipe: ChannelStub(
                Name=self.buffer_cold_pipe,
                AboutNodeName=H0N.buffer_cold_pipe,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.oat: ChannelStub(
                Name=self.oat,
                AboutNodeName=H0N.oat,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.dist_flow: ChannelStub(
                Name=self.dist_flow,
                AboutNodeName=H0N.dist_flow,
                TelemetryName=TelemetryName.GpmTimes100,
            ),
            self.primary_flow: ChannelStub(
                Name=self.primary_flow,
                AboutNodeName=H0N.primary_flow,
                TelemetryName=TelemetryName.GpmTimes100,
            ),
            self.store_flow: ChannelStub(
                Name=self.store_flow,
                AboutNodeName=H0N.store_flow,
                TelemetryName=TelemetryName.GpmTimes100,
            ),
            self.buffer.depth1: ChannelStub(
                Name=self.buffer.depth1,
                AboutNodeName=H0N.buffer.depth1,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer.depth2: ChannelStub(
                Name=self.buffer.depth2,
                AboutNodeName=H0N.buffer.depth2,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
            self.buffer.depth3: ChannelStub(
                Name=self.buffer.depth3,
                AboutNodeName=H0N.buffer.depth3,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            ),
        }
        for i in self.tank:
            d[self.tank[i].depth1] = ChannelStub(
                Name=self.tank[i].depth1,
                AboutNodeName=self.tank[i].depth1,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            )
            d[self.tank[i].depth2] = ChannelStub(
                Name=self.tank[i].depth2,
                AboutNodeName=self.tank[i].depth2,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            )
            d[self.tank[i].depth3] = ChannelStub(
                Name=self.tank[i].depth3,
                AboutNodeName=self.tank[i].depth3,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
            )
        for i in self.zone:
            d[self.zone[i].temp] = ChannelStub(
                    Name=self.zone[i].temp,
                    AboutNodeName=self.zone[i].zone_name,
                    TelemetryName=TelemetryName.AirTempFTimes1000,
                )
            d[self.zone[i].set] = ChannelStub(
                    Name=self.zone[i].set,
                    AboutNodeName=self.zone[i].stat_name,
                    TelemetryName=TelemetryName.AirTempFTimes1000,
                )
            d[self.zone[i].state] = ChannelStub(
                    Name=self.zone[i].state,
                    AboutNodeName=self.zone[i].stat_name,
                    TelemetryName=TelemetryName.ThermostatState,
                )
            d[self.zone[i].whitewire_pwr] = ChannelStub(
                    Name=self.zone[i].whitewire_pwr,
                    AboutNodeName=f"{self.zone[i]}-whitewire",
                    TelemetryName=TelemetryName.PowerW,
                )
            
        return d
