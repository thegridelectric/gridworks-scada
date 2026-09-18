class House0ChannelNames:
    """House0-SPECIFIC channel names only — the krida relay-state channels keyed to
    the House0 relay board. Names shared with core / hydronic_spaceheat (the power,
    pipe-temp, flow, 010V, energy, and `vdc-relay` channels) are NOT duplicated here;
    a consumer uses CoreChannelNames / HydronicSpaceheatChannelNames directly.
    """

    # relay state channels (House0 krida board)
    tstat_common_relay_state = "tstat-common-relay"
    charge_discharge_relay_state = "charge-discharge-relay"
    hp_failsafe_relay_state = "hp-failsafe-relay"
    aquastat_ctrl_relay_state = "aquastat-ctrl-relay"
    primary_pump_scada_ops_relay_state = "primary-pump-scada-ops-relay"
    primary_pump_failsafe_relay_state = "primary-pump-failsafe-relay"
    hp_loop_on_off_relay_state = "hp-loop-on-off-relay"
    hp_loop_keep_send_relay_state = "hp-loop-keep-send-relay"
