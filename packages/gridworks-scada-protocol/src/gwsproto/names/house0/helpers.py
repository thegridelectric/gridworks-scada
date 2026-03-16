from typing import Literal, Sequence
from gwsproto.property_format import SpaceheatName
from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZoneChannelNames as HSZoneChannelNames, HydronicSpaceheatZoneNodeNames as HSZoneNodeNames

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


def krida_failsafe_relay_suffix(zone_idx: int) -> int:
    """Returns krida relay idx for ops relay from zone_idx"""
    i = zone_idx - 1
    return House0RelayIdx.base_stat + 2 * i


def krida_ops_relay_suffix(zone_idx: int) -> int:
    """Returns krida relay idx for failsafe relay zone_idx"""
    i = zone_idx - 1
    return House0RelayIdx.base_stat + 2 * i + 1

class House0Zones:

    def __init__(self, zone_names: Sequence[SpaceheatName]):

        self.nodes: dict[int, House0ZoneNodeNames] = {}
        self.channels: dict[int, House0ZoneChannelNames] = {}

        for idx, name in enumerate(zone_names, start=1):

            self.nodes[idx] = House0ZoneNodeNames(name, idx)
            self.channels[idx] = House0ZoneChannelNames(name, idx)


class House0ZoneNodeNames:
    """
    Spaceheat Node names associated to a House0 zone.
    eg
     Inherited from HydronicSpaceheat
      - zone1-down
      - zone1-down-stat
      - zone1-down-whitewire
     Specific to House0
      - relay17 (failsafe relay on Krida)
      - relay18 (ops relay on Krida)
    """
    def __init__(self, zone: str, idx: int) -> None:
        hsznn = HSZoneNodeNames(zone, idx)
        self.zone = hsznn.zone
        self.stat = hsznn.stat
        self.whitewire = hsznn.whitewire

        failsafe_idx = krida_failsafe_relay_suffix(idx)
        ops_idx = krida_ops_relay_suffix(idx)
        self.failsafe_relay = f"relay{failsafe_idx}"
        self.ops_relay= f"relay{ops_idx}"


class House0ZoneChannelNames:
    """
    Channel names associated to a House0 zone.
    eg
     Inherited from HydronicSpaceheat
      - zone1-down-temp
      - zone1-down-set
      - zone1-down-heat-call
      - zone1-down-failsafe-relay
      - zone1-down-ops-relay

    """
    def __init__(self, zone: str, idx: int) -> None:
        hszcn = HSZoneChannelNames(zone, idx)
        base = hszcn.base

        # core semantic channels (likely derived)
        self.temp = hszcn.temp
        self.set = hszcn.set
        self.heat_call = hszcn.heat_call

        # relay states
        self.failsafe_relay_state = hszcn.failsafe_relay_state
        self.ops_relay_state = hszcn.ops_relay_state

        # raw measurements
        self.whitewire_pwr = f"{base}-whitewire-pwr"
        self.stat_temp = f"{base}-stat-temp"


