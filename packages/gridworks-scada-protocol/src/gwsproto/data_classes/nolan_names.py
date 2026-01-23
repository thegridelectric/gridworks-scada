from typing import Dict, List, Literal
from pydantic import BaseModel
from gwsproto.enums import TelemetryName
from gwsproto.property_format import SpaceheatName
DEFAULT_ANALOG_READER = "analog-temp"

from gwsproto.data_classes.house_0_names import ChannelStub
class ScadaWeb:
    DEFAULT_SERVER_NAME = "default"

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


class NhN:
    #system actor nodes
    primary_scada = "s"
    ltn = "ltn"
    secondary_scada = "s2"
    leaf_ally = "la"
    local_control = "lc"
    local_control_normal = "n"
    local_control_backup = "backup"
    local_control_scada_blind = "scada-blind"
    primary_power_meter = "power-meter"
    admin = "admin" 
    auto = "auto"
    derived_generator = "derived-generator"
    pico_cycler = "pico-cycler"
    hp_boss = "hp-boss"

    # topology nodes
    # transactive nodes
    heat_pump = "heat-pump"
    buffer_top_elt = "buffer-top-elt"
    buffer_bottom_elt = "buffer-bottome-elt"
    store_top_elt = "store-top-elt"
    store_bottom_elt = "store-bottom-elt"

    # pumps
    dist_pump = "dist-pump"
    store_pump = "store-pump"

    # required pipe temperatures
    dist_unmixed_source = "dist-unmixed-source"
    dist_unmixed_return = "dist-unmixed-return"
    store_hot_pipe = "store-hot-pipe"
    store_cold_pipe = "store-cold-pipe"

    buffer = BufferNodeNames()

    # relays
    vdc_relay = "vdc-relay"
    # required flows
    dist_flow = "dist-flow"
    store_flow = "store-flow"

    dist_btu = "dist-btu"
    store_btu = "store-btu"



    def __init__(self, total_store_tanks: int, zone_list: List[str]) -> None:
        self.tank: Dict[int, TankNodeNames] = {}
        self.zone: Dict[str, ZoneNodes] = {}
        for i in range(total_store_tanks):
            self.tank[i + 1] = TankNodeNames(i + 1)
        for i in range(len(zone_list)):
            self.zone[zone_list[i]] = ZoneNodes(zone=zone_list[i], idx=i)

    def tank_index(self, node_name: str) -> int | None:
        """
        Return 1-based tank index for a tank node name.
        Raises ValueError if node_name is not a tank reader
        Returns None if node_name is not a tank
        """
        for idx, tank in self.tank.items():
            if (
                node_name == tank.reader
                or node_name in tank.depths
            ):
                return idx
        return None



class ZoneChannelNames:
    def __init__(self, zone: str, idx: int) -> None:
        self.zone_name = f"zone{idx}-{zone}".lower()
        self.temp = f"{self.zone_name}-gw-temp"
        self.whitewire_pwr=f"{self.zone_name}-whitewire-pwr"

    @property
    def all(self) -> set[str]:
        """All required channels for this zone"""
        return {
            self.temp,
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

    def device_depth(self, name: str) -> int:
        if name == self.depth1_device:
            return 1
        elif name == self.depth2_device:
            return 2
        elif name == self.depth3_device:
            return 3
        raise ValueError(f"{name} is not a device channel for {self.reader}")

    def device_to_effective(self, name: str) -> str:
        if name == self.depth1_device:
            return self.depth1
        elif name == self.depth2_device:
            return self.depth2
        elif name == self.depth3_device:
            return self.depth3
        else:
            return name

    @property
    def effective(self) -> set[str]:
        """Effective (derived) channels:buffer-depth1, buffer-depth2, buffer-depth3"""
        return {self.depth1, self.depth2, self.depth3}

    @property
    def devices(self) -> set[str]:
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
            f"| device={sorted(self.devices)}"
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
    def devices(self) -> set[str]:
        """Temperatures reported by device, e.g. TankModule3"""
        return {self.depth1_device, self.depth2_device, self.depth3_device}

    @property
    def electrical(self) -> set[str]:
        return {
            self.depth1_micro_v,
            self.depth2_micro_v,
            self.depth3_micro_v,
        }

    def device_depth(self, name: str) -> int:
        if name == self.depth1_device:
            return 1
        elif name == self.depth2_device:
            return 2
        elif name == self.depth3_device:
            return 3
        raise ValueError(f"{name} is not a device channel for {self.reader}")

    def device_to_effective(self, name: str) -> str:
        if name == self.depth1_device:
            return self.depth1
        elif name == self.depth2_device:
            return self.depth2
        elif name == self.depth3_device:
            return self.depth3
        else:
            return name

    def __repr__(self) -> str:
        return (
            f"Buffer channels | effective={sorted(self.effective)} "
            f"| device={sorted(self.devices)}"
            f"| electrical={sorted(self.electrical)}"
        )


class NhCN:
    # Power Channels
    heatpump_pwr = f"{NhN.heat_pump}-pwr"
    buffer_top_elt_pwr = f"{NhN.buffer_top_elt}-pwr"
    buffer_bottom_elt_pwr =  f"{NhN.buffer_bottom_elt}-pwr"
    store_top_elt_pwr = f"{NhN.store_top_elt}-pwr"
    store_bottom_elt_pwr = f"{NhN.store_bottom_elt}-pwr"
    dist_pump_pwr = f"{NhN.dist_pump}-pwr"
    store_pump_pwr = f"{NhN.store_pump}-pwr"

    # Temperature Channels
    dist_unmixed_source = NhN.dist_unmixed_source
    dist_unmixed_return = NhN.dist_unmixed_return
    store_hot_pipe = NhN.store_hot_pipe
    store_cold_pipe = NhN.store_cold_pipe
    buffer = BufferChannelNames()

    # Flow Channels
    dist_flow = NhN.dist_flow
    store_flow = NhN.store_flow
    dist_flow_hz = f"{NhN.dist_flow}-hz"
    store_flow_hz = f"{NhN.store_flow}-hz"

    # Derived Channels
    required_energy = "required-energy"
    usable_energy = "usable-energy"

    # Optional
    oat = "oat"


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
        """

        d = {}
        return d
