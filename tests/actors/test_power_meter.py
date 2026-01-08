import asyncio
import logging
import typing
from gwsproto.data_classes.components import ElectricMeterComponent
from actors.config import ScadaSettings
from gwsproto.data_classes.house_0_layout import House0Layout
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import GridworksSimPm1_PowerMeterDriver

from scada_app import ScadaApp
from gwproactor_test.certs import uses_tls
from gwproactor_test.certs import copy_keys
from gwsproto.data_classes.house_0_names import H0N, H0CN

import pytest
from actors.power_meter import DriverThreadSetupHelper
from actors.power_meter import PowerMeter
from actors.power_meter import PowerMeterDriverThread
from tests.utils.scada_live_test_helper import ScadaLiveTest


def test_power_meter_small():
    settings = ScadaApp.get_settings()
    settings.is_simulated = True
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    scada = scada_app.scada
    layout = scada.layout
    # Raise exception if initiating node is anything except the unique power meter node
    with pytest.raises(Exception):
        PowerMeter(H0N.primary_scada, services=scada_app)

    meter = PowerMeter(H0N.primary_power_meter, services=scada_app)
    assert isinstance(meter._sync_thread, PowerMeterDriverThread)
    driver_thread: PowerMeterDriverThread = meter._sync_thread
    driver_thread.set_async_loop(asyncio.new_event_loop(), asyncio.Queue())
    DriverThreadSetupHelper(meter.node, settings, layout, scada.logger)

    meter_node = layout.node(H0N.primary_power_meter)
    pwr_meter_channel_names = [cfg.ChannelName for cfg in meter_node.component.gt.ConfigList]
    pwr_meter_channels = set(layout.data_channels[name] for name in pwr_meter_channel_names)
    assert set(driver_thread.last_reported_telemetry_value.keys()) == pwr_meter_channels
    assert set(driver_thread.eq_reporting_config.keys()) == pwr_meter_channels
    assert set(driver_thread._last_sampled_s.keys()) == pwr_meter_channels


    ch_1 = layout.channel(H0CN.store_pump_pwr)
    assert driver_thread.last_reported_telemetry_value[ch_1] is None
    assert driver_thread.latest_telemetry_value[ch_1] is None

    # If latest_telemetry_value is None, should not report reading
    assert driver_thread.should_report_telemetry_reading(ch_1) is False
    driver_thread.update_latest_value_dicts()
    assert isinstance(driver_thread.latest_telemetry_value[ch_1], int)
    assert driver_thread.last_reported_telemetry_value[ch_1] is None

    # If last_reported_telemetry_value exists, but last_reported is None, should report
    assert driver_thread.should_report_telemetry_reading(ch_1)
    driver_thread.report_sampled_telemetry_values([ch_1])

    assert driver_thread.last_reported_telemetry_value[ch_1] == driver_thread.latest_telemetry_value[ch_1]

    driver_thread.last_reported_telemetry_value[ch_1] = driver_thread.latest_telemetry_value[ch_1]

    assert driver_thread.value_hits_async_threshold(ch_1) is False
    store_pump_capture_delta = driver_thread.eq_reporting_config[ch_1].AsyncCaptureDelta
    assert store_pump_capture_delta == 5
    driver_thread.latest_telemetry_value[ch_1] += 4
    assert driver_thread.value_hits_async_threshold(ch_1) is False

    driver_thread.latest_telemetry_value[ch_1] += 2
    assert driver_thread.value_hits_async_threshold(ch_1) is True
    assert driver_thread.should_report_telemetry_reading(ch_1) is True
    driver_thread.report_sampled_telemetry_values([ch_1])
    assert driver_thread.last_reported_telemetry_value[ch_1] == 6
    assert driver_thread.should_report_telemetry_reading(ch_1) is False

    assert driver_thread.last_reported_agg_power_w is None
    assert driver_thread.latest_agg_power_w == 0
    assert driver_thread.should_report_aggregated_power()
    driver_thread.report_aggregated_power_w()
    assert not driver_thread.should_report_aggregated_power()

    
    hp_odu = layout.node(H0N.hp_odu)
    hp_idu = layout.node(H0N.hp_idu)

    assert hp_odu.NameplatePowerW == 6000
    assert hp_idu.NameplatePowerW == 4000
    assert driver_thread.nameplate_agg_power_w == 10_000
    power_reporting_threshold_ratio = driver_thread.async_power_reporting_threshold
    assert power_reporting_threshold_ratio == 0.02
    power_reporting_threshold_w = power_reporting_threshold_ratio * driver_thread.nameplate_agg_power_w
    assert power_reporting_threshold_w == 200

    tt = layout.channel(H0CN.hp_odu_pwr)
    driver_thread.latest_telemetry_value[tt] += 100
    assert not driver_thread.should_report_aggregated_power()
    driver_thread.latest_telemetry_value[tt] += 200
    assert driver_thread.should_report_aggregated_power()
    driver_thread.report_aggregated_power_w()
    assert driver_thread.latest_agg_power_w == 300

def meter_test_layout() -> House0Layout:
    layout = House0Layout.load(ScadaSettings().paths.hardware_layout)
    meter_component = layout.component_from_node(layout.node(H0N.primary_power_meter))
    if not isinstance(meter_component, ElectricMeterComponent):
        raise TypeError(f"ERROR. Got meter component with wrong type ({type(meter_component)})")
    for config in meter_component.gt.ConfigList:
        config.CapturePeriodS = 1
    return layout


@pytest.mark.asyncio
async def test_power_meter_periodic_update(request: pytest.FixtureRequest) -> None:
    """Verify the PowerMeter sends its periodic GtShTelemetryFromMultipurposeSensor message (PowerWatts sending is
    _not_ tested here."""

    async with ScadaLiveTest(
            start_child1=True,
            child1_layout=meter_test_layout(),
            request=request,
    ) as h:
        expected_channels = [
            h.child1.hardware_layout.data_channels[H0CN.hp_odu_pwr],
            h.child1.hardware_layout.data_channels[H0CN.hp_idu_pwr],
            h.child1.hardware_layout.data_channels[H0CN.store_pump_pwr],
        ]
        h.child.delimit("Waiting for first readings", log_level=logging.WARNING)
        data = h.child1_app.scada.data
        for ch in expected_channels:
            await h.await_for(
                lambda: len(data.recent_channel_values[ch.Name]) > 0,
                f"wait for PowerMeter first readings, [{ch.Name}]",
            )

        # Verify periodic delivery.
        received_ch_counts = [
            len(data.recent_channel_values[ch.Name]) for ch in expected_channels
        ]
        for received_count, tt in zip(received_ch_counts, expected_channels):
            h.child.delimit(f"Waiting for periodic delivery from {tt.Name}", log_level=logging.WARNING)
            await h.await_for(
                lambda: len(data.recent_channel_values[ch.Name]) > received_count,
                f"wait for PowerMeter periodic update [{tt.Name}]"
            )

@pytest.mark.asyncio
async def test_async_power_update(request: pytest.FixtureRequest):
#     """Verify that when a simulated change in power is generated, Scadd and Atn both get a PowerWatts message"""
    async with ScadaLiveTest(
        request=request,
    ) as h:
        h.start_child1() # start primary scada
        h.start_parent() # start atn
        scada = h.child1_app.scada


        data = scada.data
        print(f"type of h.child1_app.scada is {type(scada)}")
        atn_received_counts = h.parent_to_child_stats.num_received_by_type
        initial = atn_received_counts['power.watts']
        print(f"atn has received {initial} power.watts messages")
        await h.await_for(
                lambda: data.latest_power_w is not None,
                "Scada wait for initial PowerWatts"
            )
        print(f"scada.data.latest_power_w is {data.latest_power_w}")

        p = typing.cast(
            PowerMeterDriverThread,
            h.child1_app.get_communicator_as_type(
                H0N.primary_power_meter,
                PowerMeter
            )._sync_thread
        )
        driver = typing.cast(
            GridworksSimPm1_PowerMeterDriver,
            p.driver
        )

        delta_w = int(p.async_power_reporting_threshold * p.nameplate_agg_power_w) + 1

        driver.fake_power_w += delta_w
        await h.await_for(
                lambda: data.latest_power_w > 0,
                "Scada wait for PowerWatts"
                )

        in_power_metering = set(filter(lambda x: x.InPowerMetering, data.layout.data_channels.values()))

        assert in_power_metering == {
            data.layout.data_channels[H0CN.hp_idu_pwr],
            data.layout.data_channels[H0CN.hp_odu_pwr]
        }

        assert data.latest_channel_values[H0CN.hp_idu_pwr] == delta_w
        assert data.latest_channel_values[H0CN.hp_odu_pwr] == delta_w

        assert data.latest_power_w == 2 * delta_w

        await h.await_for(
            lambda: atn_received_counts['power.watts'] > initial,
            "Atn wait for power.watts",
        )
        atn = h.parent_app.atn
        assert atn.data.latest_power_w == 2 * delta_w
