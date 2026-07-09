from typing import Literal, Sequence
from gwsproto.names.hydronic_spaceheat.helpers import Tanks


class House0NodeNames:
    """House0-SPECIFIC node names only. Names shared with core / hydronic_spaceheat
    (system actors, pumps, pipe temps, flows, 010V outputs, buffer, oat) are NOT
    duplicated here — a consumer uses CoreNodeNames / HydronicSpaceheatNodeNames
    directly for those.
    """

    # relay nodes (functional names; node name == relay-state channel name.
    # The krida board position lives in House0RelayIdx / relay.actor.config
    # RelayIdx, not the name.)
    vdc_relay: Literal["vdc-relay"] = "vdc-relay"
    tstat_common_relay: Literal["tstat-common-relay"] = "tstat-common-relay"
    store_charge_discharge_relay: Literal["charge-discharge-relay"] = "charge-discharge-relay"
    hp_failsafe_relay: Literal["hp-failsafe-relay"] = "hp-failsafe-relay"
    hp_scada_ops_relay: Literal["hp-scada-ops-relay"] = "hp-scada-ops-relay"
    thermistor_common_relay: Literal["thermistor-common-relay"] = "thermistor-common-relay"
    aquastat_ctrl_relay: Literal["aquastat-ctrl-relay"] = "aquastat-ctrl-relay"
    store_pump_failsafe: Literal["store-pump-failsafe-relay"] = "store-pump-failsafe-relay"
    boiler_scada_ops: Literal["boiler-scada-ops-relay"] = "boiler-scada-ops-relay"
    primary_pump_scada_ops: Literal["primary-pump-scada-ops-relay"] = "primary-pump-scada-ops-relay"
    primary_pump_failsafe: Literal["primary-pump-failsafe-relay"] = "primary-pump-failsafe-relay"
    hp_loop_on_off: Literal["hp-loop-on-off-relay"] = "hp-loop-on-off-relay"
    hp_loop_keep_send: Literal["hp-loop-keep-send-relay"] = "hp-loop-keep-send-relay"

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
            zone: House0ZoneNodeNames(zone, idx + 1)
            for idx, zone in enumerate(zone_list)
        }


class House0ZoneNodeNames:
    """Per-zone relay node names (functional; node name == relay-state channel
    name, e.g. zone1-living-rm-failsafe-relay)."""

    def __init__(self, zone: str, idx: int) -> None:
        base = f"zone{idx}-{zone}".lower()
        self.failsafe_relay = f"{base}-failsafe-relay"
        self.ops_relay = f"{base}-ops-relay"
