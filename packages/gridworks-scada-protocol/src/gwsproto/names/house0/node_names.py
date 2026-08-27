from typing import Literal, Sequence
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HNN
from gwsproto.names.hydronic_spaceheat.helpers import  HydronicSpaceheatZoneNodeNames as HZoneNodeNames
from gwsproto.names.hydronic_spaceheat.helpers import Tanks

from gwsproto.names.core.node_names import CoreNodeNames as CNN

class House0NodeNames:
    primary_scada = CNN.primary_scada
    secondary_scada = CNN.secondary_scada
    asset_power_meter = CNN.asset_power_meter
    ltn = CNN.ltn
    leaf_ally = CNN.leaf_ally
    local_control = CNN.local_control
    admin = CNN.admin
    auto = CNN.auto
    derived_generator = CNN.derived_generator

    pico_cycler = HNN.pico_cycler
    hp_boss = HNN.hp_boss
    local_control_normal = HNN.local_control_normal
    local_control_backup = HNN.local_control_backup
    local_control_scada_blind = HNN.local_control_scada_blind

    # transactive asset nodes
    hp_odu = HNN.hp_odu
    hp_idu = HNN.hp_idu


    # pumps
    dist_pump = HNN.dist_pump
    store_pump = HNN.store_pump
    primary_pump = HNN.primary_pump


    # required pipe temperatures
    dist_swt = HNN.dist_swt
    dist_rwt = HNN.dist_rwt
    hp_lwt = HNN.hp_lwt
    hp_ewt = HNN.hp_ewt
    store_hot_pipe = HNN.store_hot_pipe
    store_cold_pipe = HNN.store_cold_pipe
    buffer_hot_pipe = HNN.buffer_hot_pipe
    buffer_cold_pipe = HNN.buffer_cold_pipe

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


    # flows
    dist_flow =HNN.dist_flow
    store_flow = HNN.store_flow
    primary_flow = HNN.primary_flow

    # zero ten output
    dist_010v = "dist-010v"
    primary_010v = "primary-010v"
    store_010v = "store-010v"

    hubitat = "hubitat"

    # buffer tank
    buffer = HNN.buffer

    # instrumentation
    zero_ten_out_multiplexer = "zero-ten-multiplexer"
    analog_temp = "analog-temp"
    relay_multiplexer = "relay-multiplexer"
    dist_btu = "dist-btu"
    primary_btu = "primary-btu"
    store_btu = "store-btu"

    # Optional
    oat = HNN.oat
    buffer_cold_pipe = HNN.buffer_cold_pipe




    def __init__(self, total_store_tanks: int, zone_list: Sequence[str]) -> None:

        self.tanks = Tanks(total_store_tanks).nodes
        self.zones = {
            zone: House0ZoneNodeNames(zone, idx + 1)
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
