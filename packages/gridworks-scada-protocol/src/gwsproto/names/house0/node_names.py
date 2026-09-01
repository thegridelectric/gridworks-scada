class House0NodeNames:
    """House0-SPECIFIC node names only. Names shared with core /
    hydronic_spaceheat (system actors, pumps, pipe temps, flows, 010V outputs,
    buffer, oat, and the relays both families have) are NOT duplicated here —
    a consumer uses CoreNodeNames / HydronicSpaceheatNodeNames directly for
    those. The four name classes are disjoint.
    """

    local_control_backup = "backup"
    local_control_scada_blind = "scada-blind"

    tstat_common_relay = "tstat-common-relay"
    store_charge_discharge_relay = "charge-discharge-relay"
    hp_failsafe_relay = "hp-failsafe-relay"
    aquastat_ctrl_relay = "aquastat-ctrl-relay"
    boiler_scada_ops = "boiler-scada-ops-relay"
    primary_pump_scada_ops = "primary-pump-scada-ops-relay"
    primary_pump_failsafe = "primary-pump-failsafe-relay"
    hp_loop_on_off = "hp-loop-on-off-relay"
    hp_loop_keep_send = "hp-loop-keep-send-relay"

    # House0-specific instrumentation
    hubitat = "hubitat"
    zero_ten_out_multiplexer = "zero-ten-multiplexer"
    analog_temp = "analog-temp"
    relay_multiplexer = "relay-multiplexer"
