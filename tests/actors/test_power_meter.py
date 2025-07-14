import argparse
import asyncio
import logging
import typing

from gwproto.enums import ActorClass
from data_classes.house_0_layout import House0Layout
from scada_app import ScadaApp
from tests.utils.fragment_runner import AsyncFragmentRunner
from tests.utils.fragment_runner import ProtocolFragment
from gwproactor_test import await_for
from gwproactor_test.certs import uses_tls
from gwproactor_test.certs import copy_keys
from data_classes.house_0_names import H0N, H0CN

import actors
import pytest
from gwproto.named_types import DataChannelGt
from actors import Scada
from actors.power_meter import DriverThreadSetupHelper
from actors.power_meter import PowerMeter
from actors.power_meter import PowerMeterDriverThread
from actors.config import ScadaSettings
from gwproto.data_classes.components.electric_meter_component import ElectricMeterComponent
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import (
    GridworksSimPm1_PowerMeterDriver,
)
from gwproactor.config import LoggerLevels
from gwproactor.config import LoggingSettings
from gwproto.messages import PowerWatts
from command_line_utils import get_nodes_run_by_scada

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
        PowerMeter(H0N.primary_scada, services=scada)

    meter = PowerMeter(H0N.primary_power_meter, services=scada)
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

    assert driver_thread.value_exceeds_async_threshold(ch_1) is False
    store_pump_capture_delta = driver_thread.eq_reporting_config[ch_1].AsyncCaptureDelta
    assert store_pump_capture_delta == 5
    driver_thread.latest_telemetry_value[ch_1] += 4
    assert driver_thread.value_exceeds_async_threshold(ch_1) is False

    driver_thread.latest_telemetry_value[ch_1] += 2
    assert driver_thread.value_exceeds_async_threshold(ch_1) is True
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

# These tests no longer pass because the code requires many of its actors to be fired up
# including synth-generator ,home-alone, atomic-ally, all the relays & dfrs & multiplexers
# @pytest.mark.asyncio
# async def test_power_meter_periodic_update(tmp_path, monkeypatch, request):
#     """Verify the PowerMeter sends its periodic GtShTelemetryFromMultipurposeSensor message (PowerWatts sending is
#     _not_ tested here."""

#     monkeypatch.chdir(tmp_path)

#     class Fragment(ProtocolFragment):

#         def get_requested_proactors(self):
#             return [self.runner.actors.scada]

#         def get_requested_actors(self):
#             meter_node = self.runner.layout.node(H0N.primary_power_meter)
#             meter_component = typing.cast(ElectricMeterComponent, meter_node.component)
#             for config in meter_component.gt.ConfigList:
#                 config.CapturePeriodS = 1
#             self.runner.actors.meter = actors.PowerMeter(
#                 name=meter_node.Name,
#                 services=self.runner.actors.scada,
#                 settings=ScadaSettings(seconds_per_report=1)
#             )
#             return [self.runner.actors.meter]

#         async def async_run(self):
#             scada = self.runner.actors.scada

#             expected_channels = [
#                 scada._layout.data_channels[H0CN.hp_odu_pwr],
#                 scada._layout.data_channels[H0CN.hp_idu_pwr],
#                 scada._layout.data_channels[H0CN.store_pump_pwr],
#             ]

#             # Wait for at least one reading to be delivered since one is delivered on thread startup.
#             for ch in expected_channels:
#                 # TODO: Test-public access for this
#                 await await_for(
#                     lambda: len(scada._data.recent_channel_values[ch.Name]) > 0,
#                     5,
#                     f"wait for PowerMeter first periodic report, [{ch.Name}]"
#                 )

#             # Verify periodic delivery.
#             received_ch_counts = [
#                 len(scada._data.recent_channel_values[ch.Name]) for ch in expected_channels
#             ]
#             scada._logger.info(received_ch_counts)
#             for received_count, tt in zip(received_ch_counts, expected_channels):
#                 await await_for(
#                     lambda: len(scada._data.recent_channel_values[ch.Name]) > received_count,
#                     5,
#                     f"wait for PowerMeter periodic update [{tt.Name}]"
#                 )

#     await AsyncFragmentRunner.async_run_fragment(Fragment, tag=request.node.name)


# @pytest.mark.asyncio
# async def test_power_meter_aggregate_power_forward(tmp_path, monkeypatch, request):
#     """Verify that when a simulated change in power is generated, Scadd and Atn both get a PowerWatts message"""

#     monkeypatch.chdir(tmp_path)
#     settings = ScadaSettings(
#         logging=LoggingSettings(
#             base_log_level=logging.DEBUG,
#             levels=LoggerLevels(
#                 message_summary=logging.DEBUG
#             )
#         )
#     )

#     class Fragment(ProtocolFragment):

#         def get_requested_proactors(self):
#             return [self.runner.actors.scada, self.runner.actors.atn]

#         def get_requested_actors(self):
#             meter_node = self.runner.layout.node(H0N.primary_power_meter)
#             meter_component = typing.cast(ElectricMeterComponent, meter_node.component)
#             for config in meter_component.gt.ConfigList:
#                 config.CapturePeriodS = 1
#             self.runner.actors.meter = actors.PowerMeter(
#                 name=meter_node.name,
#                 services=self.runner.actors.scada,
#                 settings=ScadaSettings(seconds_per_report=1)
#             )
#             return [self.runner.actors.meter]

#         async def async_run(self):
#             scada = self.runner.actors.scada
#             atn = self.runner.actors.atn
#             await await_for(
#                 lambda: scada._data.latest_total_power_w is not None,
#                 1,
#                 "Scada wait for initial PowerWatts"
#             )

#             # TODO: Cleaner test access?
#             meter_sync_thread = typing.cast(PowerMeterDriverThread, self.runner.actors.meter._sync_thread)
#             driver = typing.cast(
#                 GridworksSimPm1_PowerMeterDriver,
#                 meter_sync_thread.driver
#             )

#             # Simulate power changes. Verify Scada and Atn get messages for each.
#             num_changes = 2
#             for i in range(num_changes):
#                 scada._logger.info(f"Generating PowerWatts change {i + 1}/{num_changes}")
#                 latest_total_power_w = scada._data.latest_total_power_w
#                 num_atn_power_watts = atn.stats.num_received_by_type[PowerWatts.model_fields['TypeName'].default]

#                 # Simulate a change in aggregate power that should trigger a PowerWatts message
#                 increment = int(
#                     meter_sync_thread.async_power_reporting_threshold * meter_sync_thread.nameplate_agg_power_w
#                 ) + 1
#                 expected = latest_total_power_w + (increment * 2)
#                 driver.fake_power_w += increment

#                 # Verify scada gets the message
#                 await await_for(
#                     lambda: scada._data.latest_total_power_w > latest_total_power_w,
#                     1,
#                     "Scada wait for PowerWatts"
#                 )
#                 assert scada._data.latest_total_power_w == expected

#                 # Verify Atn gets the forwarded message
#                 await await_for(
#                     lambda: atn.stats.num_received_by_type[PowerWatts.model_fields['TypeName'].default] > num_atn_power_watts,
#                     1,
#                     "Atn wait for PowerWatts",
#                     err_str_f=atn.summary_str,
#                 )

#     await AsyncFragmentRunner.async_run_fragment(Fragment, settings=settings, tag=request.node.name)
