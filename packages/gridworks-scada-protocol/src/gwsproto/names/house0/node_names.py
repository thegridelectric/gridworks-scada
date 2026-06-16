from typing import Literal, Sequence
from gwsproto.names.hydronic_spaceheat.helpers import Tanks


class House0NodeNames:
    """House0-SPECIFIC node names only. Names shared with core / hydronic_spaceheat
    (system actors, pumps, pipe temps, flows, 010V outputs, buffer, oat) are NOT
    duplicated here — a consumer uses CoreNodeNames / HydronicSpaceheatNodeNames
    directly for those.
    """

    # relay nodes (House0 krida board assignment)
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

    # House0-specific instrumentation
    hubitat = "hubitat"
    zero_ten_out_multiplexer = "zero-ten-multiplexer"
    analog_temp = "analog-temp"
    relay_multiplexer = "relay-multiplexer"
    dist_btu = "dist-btu"
    primary_btu = "primary-btu"
    store_btu = "store-btu"

    def __init__(self, total_store_tanks: int, zone_list: Sequence[str]) -> None:

        self.tanks = Tanks(total_store_tanks).nodes
        self.zones = {
            zone: House0ZoneNodeNames(idx + 1)
            for idx, zone in enumerate(zone_list)
        }


HOUSE_0_BASE_STAT_IDX = 17

def krida_failsafe_relay_suffix(zone_idx: int) -> int:
    """Returns krida relay idx for ops relay from zone_idx"""
    i = zone_idx - 1
    return HOUSE_0_BASE_STAT_IDX + 2 * i


def krida_ops_relay_suffix(zone_idx: int) -> int:
    """Returns krida relay idx for failsafe relay zone_idx"""
    i = zone_idx - 1
    return HOUSE_0_BASE_STAT_IDX + 2 * i + 1

class House0ZoneNodeNames:
    """

    """
    def __init__(self, idx: int) -> None:

        failsafe_idx = krida_failsafe_relay_suffix(idx)
        ops_idx = krida_ops_relay_suffix(idx)
        self.failsafe_relay = f"relay{failsafe_idx}"
        self.ops_relay= f"relay{ops_idx}"
