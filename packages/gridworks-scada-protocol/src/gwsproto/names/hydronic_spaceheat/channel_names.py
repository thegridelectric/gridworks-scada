from typing import Literal
from gwsproto.names.core.channel_names import CoreChannelNames as CCN
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HNN


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


class HydronicSpaceheatChannelNames:
    heat_pump_pwr = f"{HNN.heat_pump}-pwr"
    hp_odu_pwr = f"{HNN.hp_odu}-pwr"
    hp_idu_pwr = f"{HNN.hp_idu}-pwr"
    dist_pump_pwr = f"{HNN.dist_pump}-pwr"
    primary_pump_pwr = f"{HNN.primary_pump}-pwr"
    store_pump_pwr = f"{HNN.store_pump}-pwr"

    # Temperature Channels
    dist_swt = HNN.dist_swt
    dist_rwt = HNN.dist_rwt
    hp_lwt = HNN.hp_lwt
    hp_ewt = HNN.hp_ewt
    store_hot_pipe = HNN.store_hot_pipe
    store_cold_pipe = HNN.store_cold_pipe
    buffer_hot_pipe = HNN.buffer_hot_pipe
    buffer_cold_pipe = HNN.buffer_cold_pipe
    oat = HNN.oat
    buffer = BufferChannelNames()

    dist_flow = HNN.dist_flow
    primary_flow = HNN.primary_flow
    store_flow = HNN.store_flow

    dist_flow_hz = f"{HNN.dist_flow}-hz"
    primary_flow_hz = f"{HNN.primary_flow}-hz"
    store_flow_hz = f"{HNN.store_flow}-hz"

    required_energy = "required-energy"
    usable_energy = "usable-energy"

    dist_010v = "dist-010v"
    primary_010v = "primary-010v"
    store_010v = "store-010v"

    # relay state channels
    vdc_relay_state: Literal["vdc-relay"] = "vdc-relay"
    buffer_top_relay_state = "buffer-top-relay"
    buffer_bottom_relay_state = "buffer-bottom-relay"

    store_top_relay_state= "store-top-relay"
    store_bottom_relay_state = "store-bottom-relay"
    sieg_cold = HNN.sieg_cold

    
    hp_keep_seconds_x_10 = "hp-keep-seconds-x-10"



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
            f"Tank channels | effective={sorted(self.effective)} "
            f"| device={sorted(self.devices)}"
            f"| electrical={sorted(self.electrical)}"
        )


class HydronicSpaceheatZoneChannelNames:
    def __init__(self, zone_label: str, idx: int) -> None:
        self.base = f"zone{idx}-{zone_label}".lower()

        # core semantic channels (likely derived)
        self.temp = f"{self.base}-temp"
        self.set = f"{self.base}-set"
        self.heat_call = f"{self.base}-heat-call"

        # relay states
        self.failsafe_relay_state = f"{self.base}-failsafe-relay"
        self.ops_relay_state = f"{self.base}-ops-relay"
