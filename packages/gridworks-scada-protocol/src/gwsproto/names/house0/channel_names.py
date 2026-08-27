from typing import Literal, Sequence
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.helpers import Tanks
from gwsproto.names.core.channel_names import CoreChannelNames as CCN
from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZoneChannelNames as HSZoneChannelNames



class House0ChannelNames:
    asset_electric_power = CCN.asset_electric_power
    hp_odu_pwr = HCN.hp_odu_pwr
    hp_idu_pwr = HCN.hp_idu_pwr
    dist_pump_pwr = HCN.dist_pump_pwr
    primary_pump_pwr =  HCN.primary_pump_pwr
    store_pump_pwr = HCN.store_pump_pwr

    # Temperature Channels
    dist_swt = HCN.dist_swt
    dist_rwt = HCN.dist_rwt
    hp_lwt = HCN.hp_lwt
    hp_ewt = HCN.hp_ewt
    store_hot_pipe = HCN.store_hot_pipe
    store_cold_pipe = HCN.store_cold_pipe
    buffer_hot_pipe = HCN.buffer_hot_pipe
    buffer_cold_pipe = HCN.buffer_cold_pipe
    oat = HCN.oat
    buffer = HCN.buffer


    dist_flow = HCN.dist_flow
    primary_flow = HCN.primary_flow
    store_flow = HCN.primary_flow

    dist_flow_hz = HCN.dist_flow_hz
    primary_flow_hz = HCN.primary_flow_hz
    store_flow_hz = HCN.store_flow_hz

    required_energy = HCN.required_energy
    usable_energy = HCN.usable_energy

    dist_010v = HCN.dist_010v
    primary_010v = HCN.primary_010v
    store_010v = HCN.store_010v

    # relay state channels
    vdc_relay_state: Literal["vdc-relay"] = HCN.vdc_relay_state
    tstat_common_relay_state: Literal["tstat-common-relay"] = "tstat-common-relay"
    charge_discharge_relay_state: Literal["charge-discharge-relay"] = "charge-discharge-relay"
    hp_failsafe_relay_state: Literal["hp-failsafe-relay"] = "hp-failsafe-relay"
    thermistor_common_relay_state: Literal["thermistor-common-relay"] = "thermistor-common-relay"
    hp_scada_ops_relay_state: Literal["hp-scada-ops-relay"] = "hp-scada-ops-relay"
    aquastat_ctrl_relay_state: Literal["aquastat-ctrl-relay"] = "aquastat-ctrl-relay"
    store_pump_failsafe_relay_state: Literal["store-pump-failsafe-relay"] = "store-pump-failsafe-relay"
    boiler_scada_ops_relay_state: Literal["boiler-scada_ops-relay"] = "boiler-scada_ops-relay"
    primary_pump_scada_ops_relay_state: Literal["primary-pump-scada-ops-relay"] = "primary-pump-scada-ops-relay"
    primary_pump_failsafe_relay_state: Literal["primary-pump-failsafe-relay"] = "primary-pump-failsafe-relay"
    hp_loop_on_off_relay_state: Literal["hp-loop-on-off-relay"] = "hp-loop-on-off-relay"
    hp_loop_keep_send_relay_state: Literal["hp-loop-keep-send-relay"] = "hp-loop-keep-send-relay"

    def __init__(self, total_store_tanks: int, zone_list: Sequence[str]):
        self.tanks = Tanks(total_store_tanks).channels
        self.zones = {
            name: House0ZoneChannelNames(name, i + 1)
            for i, name in enumerate(zone_list) 
        }


class House0ZoneChannelNames:
    """
    zone1-living-rm-whitewire-pwr, zone1-living-rm-stat-temp
    """
    def __init__(self, zone: str, idx: int) -> None:
        base = HSZoneChannelNames(zone, idx).base

        # raw measurements
        self.whitewire_pwr = f"{base}-whitewire-pwr"
        self.stat_temp = f"{base}-stat-temp"
