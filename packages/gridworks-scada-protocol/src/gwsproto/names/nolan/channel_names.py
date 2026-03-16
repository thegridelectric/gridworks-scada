from typing import Sequence
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.helpers import Tanks
from gwsproto.names.core.channel_names import CoreChannelNames as CCN
from gwsproto.names.nolan.node_names import NolanNodeNames as NNN
from gwsproto.names.nolan.helpers import NolanZoneChannelNames

class NolanChannelNames:
    asset_electric_power = CCN.asset_electric_power
    heat_pump_pwr = HCN.heat_pump_pwr
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
    vdc_relay_state = HCN.vdc_relay_state
    buffer_top_relay_state = NNN.buffer_top_relay
    buffer_bottom_relay_state = NNN.buffer_bottom_relay
    store_top_relay_state = NNN.store_top_relay
    store_bottom_relay_state = NNN.store_bottom_relay

    def __init__(self, total_store_tanks: int, zone_list: Sequence[str]):
        self.tanks = Tanks(total_store_tanks).channels
        self.zones = {
            name: NolanZoneChannelNames(name, i + 1)
            for i, name in enumerate(zone_list) 
        }