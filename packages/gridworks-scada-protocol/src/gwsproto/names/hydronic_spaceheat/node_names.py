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
    """Node names every hydronic spaceheat plant has, whatever its family.

    Disjoint from CoreNodeNames (system actor nodes), House0NodeNames and
    NolanNodeNames (family-specific): a name shared by two families lives
    here, and is declared nowhere else.
    """

    pico_cycler = "pico-cycler"
    hp_boss = "hp-boss"

    # transactive asset nodes
    # For monoblocs, hp-odu IS the heat pump (there is no hp-idu, though
    # there MAY be an hp-ctrl-box).
    hp_odu = "hp-odu"
    # The heat pump's indoor unit when it carries its own refrigerant
    # cycle/compressor stage (the cascade hydro kits). NOT a monobloc's indoor
    # box — that is hp-ctrl-box.
    hp_idu = "hp-idu"
    # A monobloc's indoor box: control electronics, the water-pump feed, and the
    # backup heater — no compressor. Deliberately NOT hp-idu.
    hp_ctrl_box = "hp-ctrl-box"
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

    # Required flow
    dist_flow = "dist-flow"
    store_flow = "store-flow"
    primary_flow = "primary-flow"

    # dac outputs
    dist_010v = "dist-010v"
    primary_010v = "primary-010v"
    store_010v = "store-010v"

    # relays
    vdc_relay = "vdc-relay"
    hp_scada_ops_relay = "hp-scada-ops-relay"
    store_pump_relay = "store-pump-relay"

    # buffer tank
    buffer = BufferNodeNames()  # set below

    sieg_flow = "sieg-flow"
    sieg_cold = "sieg-cold"
    sieg_loop = "sieg-loop"
    sieg_send = "sieg-send"
    
    oat = "oat"

    # instrumentation
    dist_btu = "dist-btu"
    primary_btu = "primary-btu"
    store_btu = "store-btu"

class HydronicSpaceheatZoneNodeNames:

    """
    Spaceheat Node names associated to a zone:
    self.zone, self.stat, self.whitewire, self.failsafe_relay, self.ops_relay

    Every family names a zone's two relays the same way, so they are here
    rather than in the per-family zone classes.
    """
    def __init__(self, zone_label: str, idx: int) -> None:
        self.zone =  f"zone{idx}-{zone_label}".lower()
        self.stat = f"{self.zone}-stat"
        self.whitewire=f"{self.zone}-whitewire"

        # Hands the zone's heat call between wall thermostat and scada
        self.failsafe_relay = f"{self.zone}-failsafe-relay"
        # Sends the scada's heat call when failsafe is switched to scada
        self.ops_relay = f"{self.zone}-ops-relay"


class FlowNodeNames:
    """
    Spaceheat Node name for a flow meter at a position (dist/primary/store/sieg).

    self.flow == f"{position}-flow" (e.g. dist-flow), the same value as the fixed
    HydronicSpaceheatNodeNames.dist_flow/primary_flow/store_flow attributes — this
    is the parametric form for a config-supplied position.
    """

    def __init__(self, position: str) -> None:
        self.position = position
        self.flow = f"{position}-flow"

    def __repr__(self) -> str:
        return f"Flow node {self.flow}"


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