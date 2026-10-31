HORIZON = 48

_LMP_USD_MWH = [
    43.8,
    39.4,
    39.77,
    44.93,
    52.55,
    62.07,
    55.12,
    81.51,
    89.04,
    54.29,
    54.02,
    48.58,
    40.49,
    46.62,
    50.71,
    41.16,
    40.98,
    39.87,
    39.29,
    41.63,
    59.78,
    90.27,
    94.87,
    59.6,
    43.8,
    39.4,
    39.77,
    44.93,
    52.55,
    62.07,
    55.12,
    81.51,
    89.04,
    54.29,
    54.02,
    48.58,
    40.49,
    46.62,
    50.71,
    41.16,
    40.98,
    39.87,
    39.29,
    41.63,
    59.78,
    90.27,
    94.87,
    59.6,
]

_DIST_USD_MWH = [
    487.63,
    487.63,
    487.63,
    54.98,
    54.98,
    54.98,
    54.98,
    487.63,
    487.63,
    487.63,
    487.63,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    487.63,
    487.63,
    487.63,
    487.63,
    487.63,
    54.98,
    54.98,
    54.98,
    54.98,
    487.63,
    487.63,
    487.63,
    487.63,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    50.13,
    487.63,
    487.63,
]

_OAT_F = [
    39.0,
    42.0,
    46.0,
    49.0,
    50.0,
    51.0,
    52.0,
    50.0,
    49.0,
    47.0,
    45.0,
    45.0,
    45.0,
    44.0,
    43.0,
    43.0,
    42.0,
    41.0,
    40.0,
    40.0,
    38.0,
    38.0,
    40.0,
    41.0,
    43.0,
    45.0,
    47.0,
    47.0,
    47.0,
    47.0,
    46.0,
    45.0,
    43.0,
    41.0,
    40.0,
    39.0,
    39.0,
    38.0,
    38.0,
    38.0,
    37.0,
    37.0,
    36.0,
    35.0,
    34.0,
    33.0,
    34.0,
    37.0,
]


def get_sample_heat_pump_water_tank_params():
    from bruce.graph_optimizer.assets.heat_pump_water_tank import HeatPumpWaterTankParams

    elec_price_mwh = [
        lmp + dist for lmp, dist in zip(_LMP_USD_MWH, _DIST_USD_MWH, strict=True)
    ]
    return HeatPumpWaterTankParams(
        horizon=HORIZON,
        start_unix_s=1762178400,
        site_id="hw1.isone.me.versant.keene.beech.scada",
        num_layers=24,
        storage_volume_gallons=120.0,
        storage_losses_percent=0.5,
        hp_max_kw_elec=11.0,
        hp_turn_on_minutes=10,
        initial_top_temp=166.0,
        initial_middle_temp=158.0,
        initial_bottom_temp=87.0,
        initial_thermocline1=8,
        initial_thermocline2=16,
        hp_currently_on=False,
        elec_price_mwh=elec_price_mwh,
        oat_f=list(_OAT_F),
        load_kwh=[5.0] * HORIZON,
        rswt_f=[140.0] * HORIZON,
        cop_intercept=1.02,
        cop_oat_coeff=0.0257,
        cop_lwt_coeff=0.0,
        cop_min=1.4,
        cop_min_oat_f=15.0,
    )


# def test_heat_pump_flo_graph_build_and_bid():
#     """Requires editable install: pip install -e ../../optimal-flexibility (see tools/mkenv.sh)."""
#     params = get_sample_heat_pump_water_tank_params()
#     from bruce.graph_optimizer.assets.heat_pump_water_tank import HeatPumpWaterTankAsset
#     from bruce.graph_optimizer.graph import Graph
#
#     asset = HeatPumpWaterTankAsset(params)
#     graph = Graph(asset)
#     graph.find_shortest_path()
#     graph.trim_graph_for_waiting()
#     pq_pairs = graph.generate_bid(
#         forecast_price_mwh=params.elec_price_mwh[0],
#         updated_params=params,
#     )
#     assert len(pq_pairs) >= 2
#     assert pq_pairs[0].price_mwh == -100
#     quantities = [p.quantity_kwh for p in pq_pairs]
#     for i in range(len(quantities) - 1):
#         assert quantities[i] <= quantities[i + 1] + 0.01

if __name__ == "__main__":
    from bruce.graph_optimizer.assets.heat_pump_water_tank import HeatPumpWaterTankAsset
    from bruce.graph_optimizer.graph import Graph

    params = get_sample_heat_pump_water_tank_params()
    asset = HeatPumpWaterTankAsset(params)
    graph = Graph(asset)
    graph.find_shortest_path()
    graph.trim_graph_for_waiting()
    pq_pairs = graph.generate_bid(
        forecast_price_mwh=params.elec_price_mwh[0],
        updated_params=params,
    )
    assert len(pq_pairs) >= 2
    assert pq_pairs[0].price_mwh == -100
    quantities = [p.quantity_kwh for p in pq_pairs]
    for i in range(len(quantities) - 1):
        assert quantities[i] <= quantities[i + 1] + 0.01
