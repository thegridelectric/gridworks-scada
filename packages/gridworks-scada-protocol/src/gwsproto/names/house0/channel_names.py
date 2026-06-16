from typing import Literal, Sequence
from gwsproto.names.hydronic_spaceheat.helpers import Tanks
from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZoneChannelNames as HSZoneChannelNames



class House0ChannelNames:
    """House0-SPECIFIC channel names only — the krida relay-state channels keyed to
    the House0 relay board. Names shared with core / hydronic_spaceheat (the power,
    pipe-temp, flow, 010V, energy, and `vdc-relay` channels) are NOT duplicated here;
    a consumer uses CoreChannelNames / HydronicSpaceheatChannelNames directly.
    """

    # relay state channels (House0 krida board)
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
    """House0-SPECIFIC zone channels only. The hydronic-shared zone channels
    (temp/set/heat_call/gw_microvolts/failsafe_relay_state/ops_relay_state) live on
    HydronicSpaceheatZoneChannelNames — a consumer uses that class directly when those
    are the appropriate names; this class does NOT compose from or duplicate them.

    e.g. zone1-living-rm-whitewire-pwr, zone1-living-rm-stat-temp
    """
    def __init__(self, zone: str, idx: int) -> None:
        base = HSZoneChannelNames(zone, idx).base
        self.whitewire_pwr = f"{base}-whitewire-pwr"
        self.stat_temp = f"{base}-stat-temp"
