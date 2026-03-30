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
    store_pump = "store-pump"

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

    # relays
    vdc_relay = "vdc_relay"

    # buffer tank
    buffer = BufferNodeNames()  # set below

    sieg_flow = "sieg-flow"
    sieg_cold = "sieg-cold"
    sieg_loop = "sieg-loop"
    
    oat = "oat"


class HydronicSpaceheatZoneNodeNames:

    """
    Spaceheat Node names associated to a zone:
    self.zone_name, self.stat, self.whitewire
"""
    def __init__(self, zone_label: str, idx: int) -> None:
        self.zone =  f"zone{idx}-{zone_label}".lower()
        self.stat = f"{self.zone}-stat"
        self.whitewire=f"{self.zone}-whitewire"


class TankNodeNames: 
    """
    Spaceheat Node names associated to the buffer"

    self.reader, self.depth1, self.depth2, self.depth3
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


HydronicSpaceheatNodeNames.buffer = BufferNodeNames()