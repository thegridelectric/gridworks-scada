from typing import Dict, List
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


class H0N:
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


#-------------------------------------------------------------
# House 0 Channels
#--------------------------------------------------------------


class ZoneChannelNames:
    def __init__(self, zone: str, idx: int) -> None:
        self.zone_name = f"zone{idx}-{zone}".lower()
        self.stat_name = f"{self.zone_name}-stat"
        self.temp = f"{self.zone_name}-temp"
        self.set = f"{self.zone_name}-set"
        # SICK / UNSTABLE values — do not trust for heat-call or control. This is
        # the Hubitat's `thermostatOperatingState` report, which has been very
        # inaccurate; the trustworthy heat-call signal is the `-heat-call`
        # DerivedChannel computed from whitewire power (see
        # derived_generator.handle_heat_call). NOTE: it is still listed in `.all`
        # below, so right now it is REQUIRED (back-compat for the dashboard
        # consumers); the direction is to demote it to known-optional once
        # whitewire-derived heat-call is the relied-on signal everywhere.
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


class H0CN:
    def __init__(self, total_store_tanks: int, zone_list: List[str]) -> None:
        self.tank: Dict[int, TankChannelNames] = {}
        self.zone: Dict[int, ZoneChannelNames] = {}
        for i in range(total_store_tanks):
            self.tank[i + 1] = TankChannelNames(i + 1)
        for i in range(len(zone_list)):
            self.zone[i + 1] = ZoneChannelNames(zone=zone_list[i], idx=i + 1)
