import argparse
import logging
import typing
from test.fragment_runner import AsyncFragmentRunner
from test.fragment_runner import ProtocolFragment
from test.utils import await_for

import actors2
import pytest
from actors2 import Scada2
from actors2.power_meter import DriverThreadSetupHelper
from actors2.power_meter import PowerMeter
from actors2.power_meter import PowerMeterDriverThread
from config import ScadaSettings
from data_classes.components.electric_meter_component import ElectricMeterComponent
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import (
    GridworksSimPm1_PowerMeterDriver,
)
from load_house import load_all
from logging_config import LoggerLevels
from logging_config import LoggingSettings
from logging_setup import setup_logging
from named_tuples.telemetry_tuple import TelemetryTuple
from schema.enums import TelemetryName
from schema.messages import GsPwr_Maker


def test_power_meter_small():
    settings = ScadaSettings()
    layout = load_all(settings)
    scada = Scada2("a.s", settings, layout)

    # Raise exception if initiating node is anything except the unique power meter node
    with pytest.raises(Exception):
        PowerMeter("a.s", services=scada)

    meter = PowerMeter("a.m", services=scada)
    assert isinstance(meter._sync_thread, PowerMeterDriverThread)
    driver_thread: PowerMeterDriverThread = meter._sync_thread
    setup_helper = DriverThreadSetupHelper(meter.node, settings, layout)

    assert set(driver_thread.nameplate_telemetry_value.keys()) == set(
        layout.all_power_meter_telemetry_tuples
    )
    assert set(driver_thread.last_reported_telemetry_value.keys()) == set(
        layout.all_power_meter_telemetry_tuples
    )
    assert set(driver_thread.latest_telemetry_value.keys()) == set(layout.all_power_meter_telemetry_tuples)
    assert set(driver_thread.eq_reporting_config.keys()) == set(layout.all_power_meter_telemetry_tuples)
    assert set(driver_thread._last_sampled_s.keys()) == set(layout.all_power_meter_telemetry_tuples)

    # Only get resistive heater nameplate attributes if node role is boost element
    with pytest.raises(Exception):
        setup_helper.get_resistive_heater_nameplate_power_w(layout.node("a.tank.temp0"))

    with pytest.raises(Exception):
        setup_helper.get_resistive_heater_nameplate_current_amps(layout.node("a.tank.temp0"))

    all_eq_configs = driver_thread.reporting_config.ElectricalQuantityReportingConfigList

    amp_list = list(
        filter(
            lambda x: x.TelemetryName == TelemetryName.CURRENT_RMS_MICRO_AMPS
            and x.ShNodeAlias == "a.elt1",
            all_eq_configs,
        )
    )
    assert (len(amp_list)) == 1
    tt = TelemetryTuple(
        AboutNode=layout.node("a.elt1"),
        SensorNode=meter.node,
        TelemetryName=TelemetryName.CURRENT_RMS_MICRO_AMPS,
    )
    assert tt in layout.all_power_meter_telemetry_tuples
    assert driver_thread.last_reported_telemetry_value[tt] is None
    assert driver_thread.latest_telemetry_value[tt] is None

    # If latest_telemetry_value is None, should not report reading
    assert driver_thread.should_report_telemetry_reading(tt) is False
    driver_thread.update_latest_value_dicts()
    assert isinstance(driver_thread.latest_telemetry_value[tt], int)
    assert driver_thread.last_reported_telemetry_value[tt] is None

    # If last_reported_telemetry_value exists, but last_reported is None, should report
    assert driver_thread.should_report_telemetry_reading(tt)
    driver_thread.report_sampled_telemetry_values([tt])

    assert driver_thread.last_reported_telemetry_value[tt] == driver_thread.latest_telemetry_value[tt]

    driver_thread.last_reported_telemetry_value[tt] = driver_thread.latest_telemetry_value[tt]

    assert driver_thread.value_exceeds_async_threshold(tt) is False
    report_threshold_ratio = driver_thread.eq_reporting_config[tt].AsyncReportThreshold
    assert driver_thread.nameplate_telemetry_value[tt] == 18750000
    assert report_threshold_ratio == 0.02
    report_threshold_microamps = driver_thread.nameplate_telemetry_value[tt] * 0.02
    assert report_threshold_microamps == 375000

    driver_thread.latest_telemetry_value[tt] += 374000
    assert driver_thread.value_exceeds_async_threshold(tt) is False

    driver_thread.latest_telemetry_value[tt] += 10000
    assert driver_thread.value_exceeds_async_threshold(tt) is True
    assert driver_thread.should_report_telemetry_reading(tt) is True
    driver_thread.report_sampled_telemetry_values([tt])
    assert driver_thread.last_reported_telemetry_value[tt] == 402000
    assert driver_thread.should_report_telemetry_reading(tt) is False

    assert driver_thread.last_reported_agg_power_w is None
    assert driver_thread.latest_agg_power_w == 0
    assert driver_thread.should_report_aggregated_power()
    driver_thread.report_aggregated_power_w()
    assert not driver_thread.should_report_aggregated_power()

    nameplate_pwr_w_1 = setup_helper.get_resistive_heater_nameplate_power_w(layout.node("a.elt1"))
    nameplate_pwr_w_2 = setup_helper.get_resistive_heater_nameplate_power_w(layout.node("a.elt2"))
    assert nameplate_pwr_w_1 == 4500
    assert nameplate_pwr_w_2 == 4500
    assert driver_thread.nameplate_agg_power_w == 9000
    power_reporting_threshold_ratio = driver_thread.async_power_reporting_threshold
    assert power_reporting_threshold_ratio == 0.02
    power_reporting_threshold_w = power_reporting_threshold_ratio * driver_thread.nameplate_agg_power_w
    assert power_reporting_threshold_w == 180

    tt = TelemetryTuple(
        AboutNode=layout.node("a.elt1"),
        SensorNode=meter.node,
        TelemetryName=TelemetryName.POWER_W,
    )
    driver_thread.latest_telemetry_value[tt] += 100
    assert not driver_thread.should_report_aggregated_power()
    driver_thread.latest_telemetry_value[tt] += 100
    assert driver_thread.should_report_aggregated_power()
    driver_thread.report_aggregated_power_w()
    assert driver_thread.latest_agg_power_w == 200


@pytest.mark.asyncio
async def test_power_meter_periodic_update(tmp_path, monkeypatch):
    """Verify the PowerMeter sends its periodic GtShTelemetryFromMultipurposeSensor message (GsPwr sending is
    _not_ tested here."""

    monkeypatch.chdir(tmp_path)
    logging.basicConfig(level="DEBUG")

    class Fragment(ProtocolFragment):

        def get_requested_actors(self):
            return [self.runner.actors.scada2]

        def get_requested_actors2(self):
            meter_node = self.runner.layout.node("a.m")
            meter_cac = typing.cast(ElectricMeterComponent, meter_node.component).cac
            monkeypatch.setattr(meter_cac, "update_period_ms", 0)
            self.runner.actors.meter2 = actors2.PowerMeter(
                name=meter_node.alias,
                services=self.runner.actors.scada2,
                settings=ScadaSettings(seconds_per_report=1)
            )
            return [self.runner.actors.meter2]

        async def async_run(self):
            scada = self.runner.actors.scada2

            expected_tts = [
                TelemetryTuple(
                    AboutNode=self.runner.layout.node("a.elt1"),
                    SensorNode=self.runner.actors.meter2.node,
                    TelemetryName=TelemetryName.CURRENT_RMS_MICRO_AMPS,
                ),
                TelemetryTuple(
                    AboutNode=self.runner.layout.node("a.elt1"),
                    SensorNode=self.runner.actors.meter2.node,
                    TelemetryName=TelemetryName.POWER_W,
                )
            ]

            # Wait for at least one reading to be delivered since one is delivered on thread startup.
            for tt in expected_tts:
                # TODO: Test-public access for this
                await await_for(
                    lambda: len(scada._data.recent_values_from_multipurpose_sensor[tt]) > 0,
                    5,
                    f"wait for PowerMeter first periodic report, [{tt.TelemetryName}]"
                )

            # Verify pediodic delivery.
            received_tt_counts = [
                len(scada._data.recent_values_from_multipurpose_sensor[tt]) for tt in expected_tts
            ]
            scada._logger.info(received_tt_counts)
            for received_count, tt in zip(received_tt_counts, expected_tts):
                await await_for(
                    lambda: len(scada._data.recent_values_from_multipurpose_sensor[tt]) > received_count,
                    5,
                    f"wait for PowerMeter periodic update [{tt.TelemetryName}]"
                )

    await AsyncFragmentRunner.async_run_fragment(Fragment)


@pytest.mark.asyncio
async def test_power_meter_aggregate_power_forward2(tmp_path, monkeypatch):
    """Verify that when a simulated change in power is generated, Scadd and Atn both get a GsPwr message"""

    monkeypatch.chdir(tmp_path)
    settings = ScadaSettings(
        logging=LoggingSettings(
            base_log_level=logging.DEBUG,
            levels=LoggerLevels(
                message_summary=logging.DEBUG
            )
        )
    )
    settings.paths.mkdirs()
    errors = []
    setup_logging(args=argparse.Namespace(), settings=settings, errors=errors)
    assert not errors

    class Fragment(ProtocolFragment):

        def get_requested_actors(self):
            return [self.runner.actors.scada2, self.runner.actors.atn]

        def get_requested_actors2(self):
            meter_node = self.runner.layout.node("a.m")
            meter_cac = typing.cast(ElectricMeterComponent, meter_node.component).cac
            monkeypatch.setattr(meter_cac, "update_period_ms", 0)
            self.runner.actors.meter2 = actors2.PowerMeter(
                name=meter_node.alias,
                services=self.runner.actors.scada2,
                settings=ScadaSettings(seconds_per_report=1)
            )
            return [self.runner.actors.meter2]

        async def async_run(self):
            scada = self.runner.actors.scada2
            atn = self.runner.actors.atn
            atn.logger.setLevel(logging.DEBUG)
            await await_for(
                lambda: scada._data.latest_total_power_w is not None,
                1,
                "Scada wait for initial GsPwr"
            )

            # TODO: Cleaner test access?
            meter_sync_thread = typing.cast(PowerMeterDriverThread, self.runner.actors.meter2._sync_thread)
            driver = typing.cast(
                GridworksSimPm1_PowerMeterDriver,
                meter_sync_thread.driver
            )

            # Simulate power changes. Verify Scada and Atn get messages for each.
            num_changes = 5
            for i in range(num_changes):
                scada._logger.info(f"Generating GsPwr change {i + 1}/{num_changes}")
                latest_total_power_w = scada._data.latest_total_power_w
                num_atn_gs_pwr = atn.num_received_by_topic[GsPwr_Maker.type_alias]

                # Simulate a change in aggregate power that should trigger a GsPwr message
                increment = int(
                    meter_sync_thread.async_power_reporting_threshold * meter_sync_thread.nameplate_agg_power_w
                ) + 1
                expected = latest_total_power_w + (increment * scada.GS_PWR_MULTIPLIER
                                                   * len(self.runner.layout.all_power_tuples))
                driver.fake_power_w += increment

                # Verify scada gets the message
                await await_for(
                    lambda: scada._data.latest_total_power_w > latest_total_power_w,
                    1,
                    "Scada wait for GsPwr"
                )
                assert scada._data.latest_total_power_w == expected

                # Verify Atn gets the forwarded message
                await await_for(
                    lambda: atn.num_received_by_topic[GsPwr_Maker.type_alias] > num_atn_gs_pwr,
                    1,
                    "Atn wait for GsPwr",
                    err_str_f=atn.summary_str,
                )

    await AsyncFragmentRunner.async_run_fragment(Fragment, settings=settings)
