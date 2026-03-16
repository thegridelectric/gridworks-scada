from gwsproto.names.core.channel_names import CoreChannelNames as CCN
from gwsproto.names.hydronic_spaceheat.helpers import BufferChannelNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HNN


class HydronicSpaceheatChannelNames:
    asset_electric_power = CCN.asset_electric_power
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
    store_flow = HNN.primary_flow

    dist_flow_hz = f"{HNN.dist_flow}-hz"
    primary_flow_hz = f"{HNN.primary_flow}-hz"
    store_flow_hz = f"{HNN.store_flow}-hz"

    required_energy = "required-energy"
    usable_energy = "usable-energy"

    dist_010v = "dist-010v"
    primary_010v = "primary_010v"
    store_010v = "store_010v"

    # relay state channels
    vdc_relay_state = "vdc_relay"
    
