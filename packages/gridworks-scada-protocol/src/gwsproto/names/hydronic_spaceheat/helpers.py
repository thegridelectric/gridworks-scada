from typing import Sequence

from gwsproto.property_format import SpaceheatName



class HydronicSpaceheatZones:

    def __init__(self, zone_names: Sequence[SpaceheatName]):

        self.nodes: dict[int, HydronicSpaceheatZoneNodeNames] = {}
        self.channels: dict[int, HydronicSpaceheatZoneChannelNames] = {}

        for idx, name in enumerate(zone_names, start=1):

            self.nodes[idx] = HydronicSpaceheatZoneNodeNames(name, idx)
            self.channels[idx] = HydronicSpaceheatZoneChannelNames(name, idx)



class HydronicSpaceheatZoneNodeNames:
    """
    Spaceheat Node names associated to a zone:
    self.zone_name, self.stat, self.whitewire
    """
    def __init__(self, zone_label: str, idx: int) -> None:
        self.zone =  f"zone{idx + 1}-{zone_label}".lower()

        self.stat = f"{self.zone}-stat"
        self.whitewire=f"{self.zone}-whitewire"



class HydronicSpaceheatZoneChannelNames:
    def __init__(self, zone_label: str, idx: int) -> None:
        self.base = f"zone{idx + 1}-{zone_label}".lower()

        # core semantic channels (likely derived)
        self.temp = f"{self.base}-temp"
        self.set = f"{self.base}-set"
        self.heat_call = f"{self.base}-heat-call"

        # relay states
        self.failsafe_relay_state = f"{self.base}-failsafe-relay"
        self.ops_relay_state = f"{self.base}-ops-relay"


class Tanks:

    def __init__(self, total_store_tanks: int):
        self.nodes: dict[int, TankNodeNames] = {}
        self.channels: dict[int, TankChannelNames] = {}

        for idx in range(total_store_tanks):
            self.nodes[idx+1] = TankNodeNames(idx + 1)
            self.channels[idx+1] = TankChannelNames(idx + 1)


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

    def effective_to_device(self, name: str) -> str:
        if name == self.depth1:
            return self.depth1_device
        elif name == self.depth2:
            return self.depth2_device
        elif name == self.depth3:
            return self.depth3_device
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

    def effective_to_device(self, name: str) -> str:
        if name == self.depth1:
            return self.depth1_device
        elif name == self.depth2:
            return self.depth2_device
        elif name == self.depth3:
            return self.depth3_device
        else:
            return name

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
