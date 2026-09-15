from typing import Dict
DEFAULT_ANALOG_READER = "analog-temp"


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
    def __init__(self, total_store_tanks: int) -> None:
        self.tank: Dict[int, TankNodeNames] = {}
        for i in range(total_store_tanks):
            self.tank[i + 1] = TankNodeNames(i + 1)

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
    def __init__(self, total_store_tanks: int) -> None:
        self.tank: Dict[int, TankChannelNames] = {}
        for i in range(total_store_tanks):
            self.tank[i + 1] = TankChannelNames(i + 1)
