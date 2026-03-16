from gwsproto.names.hydronic_spaceheat.helpers import BufferNodeNames


class HydronicSpaceheatNodeNames:

    # local control nodes
    local_control_normal = "n"
    local_control_backup = "backup"
    local_control_scada_blind = "scada-blind"

    pico_cycler = "pico-cycler"
    hp_boss = "hp-boss"

    # transactive asset nodes
    heat_pump = "heat-pump" # Allow for this when monoblock??
    hp_odu = "hp-odu"
    hp_idu = "hp_idu"
    buffer_top_elt = "buffer-top-elt"
    buffer_bottom_elt = "buffer-bottom-elt"
    store_top_elt = "store-top-elt"
    store_bottom_elt = "store-bottom-elt"

    # pumps
    dist_pump = "dist-pump"
    primary_pump = "primary-pump"
    store_pump = "store_pump"

    # required pipe temperatures
    dist_swt = "dist-swt"
    dist_rwt = "dist-rwt"
    hp_lwt = "hp-lwt"
    hp_ewt = "hp-ewt"
    store_hot_pipe = "store-hot-pipe"
    store_cold_pipe = "store-cold-pipe"
    buffer_hot_pipe = "buffer-hot-pipe"

    # sometimes 
    buffer_cold_pipe = "buffer-cold-pipe"

    # flows
    dist_flow = "dist-flow"
    store_flow = "store-flow"
    primary_flow = "primary_flow"

    dist_010v = "dist-010v"
    primary_010v = "primary-010v"
    store_010v = "store-010v"

    # buffer tank
    buffer = BufferNodeNames()
    
    oat = "oat"
