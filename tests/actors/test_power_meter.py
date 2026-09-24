import asyncio
import logging
import typing
from gwsproto.data_classes.components import ElectricMeterComponent
from actors.config import ScadaSettings
from pathlib import Path
from sema_to_dc import load_layout
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import GridworksSimPm1_PowerMeterDriver

from scada_app import ScadaApp
from gwproactor_test.certs import uses_tls
from gwproactor_test.certs import copy_keys
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from gwproto import Message
from gwsproto.named_types import ChannelFlatlined, PowerWatts, SyncedReadings

import pytest
from actors.power_meter import DriverThreadSetupHelper
from actors.power_meter import PowerMeter
from actors.power_meter import PowerMeterDriverThread
from tests.utils.scada_live_test_helper import ScadaLiveTest


def test_power_meter_small():
    settings = ScadaApp.get_settings()
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    scada = scada_app.scada
    layout = scada.layout
    # Raise exception if initiating node is anything except the unique power meter node
    with pytest.raises(Exception):
        PowerMeter(CoreNodeNames.primary_scada, services=scada_app)

    meter = PowerMeter(CoreNodeNames.asset_power_meter, services=scada_app)
    assert isinstance(meter._sync_thread, PowerMeterDriverThread)
    driver_thread: PowerMeterDriverThread = meter._sync_thread
    driver_thread.set_async_loop(asyncio.new_event_loop(), asyncio.Queue())
    DriverThreadSetupHelper(meter.node, settings, layout, scada.logger)

    meter_node = layout.node(CoreNodeNames.asset_power_meter)
    # the meter reads its ConfigList less the layout's disabled channels
    pwr_meter_channel_names = layout.enabled_channel_names(
        cfg.ChannelName for cfg in meter_node.component.gt.ConfigList
    )
    pwr_meter_channels = set(layout.data_channels[name] for name in pwr_meter_channel_names)
    assert set(driver_thread.last_reported_telemetry_value.keys()) == pwr_meter_channels
    assert set(driver_thread.eq_reporting_config.keys()) == pwr_meter_channels
    assert set(driver_thread._last_sampled_s.keys()) == pwr_meter_channels


    ch_1 = layout.channel(HCN.secondary_pump_pwr)
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
    secondary_pump_capture_delta = driver_thread.tuning_by_ch[ch_1].AsyncCaptureDelta
    assert secondary_pump_capture_delta == 5
    driver_thread.latest_telemetry_value[ch_1] += 4
    assert driver_thread.value_hits_async_threshold(ch_1) is False

    driver_thread.latest_telemetry_value[ch_1] += 2
    assert driver_thread.value_hits_async_threshold(ch_1) is True
    assert driver_thread.should_report_telemetry_reading(ch_1) is True
    driver_thread.report_sampled_telemetry_values([ch_1])
    assert driver_thread.last_reported_telemetry_value[ch_1] == 6
    assert driver_thread.should_report_telemetry_reading(ch_1) is False

    assert driver_thread.last_reported_agg_power_w is None
    # secondary-pump-pwr sits inside the transactive boundary, so the 6 W bumped
    # onto ch_1 above already shows in the aggregate.
    assert driver_thread.latest_agg_power_w == 6
    assert driver_thread.should_report_aggregated_power()
    driver_thread.report_aggregated_power_w()
    assert not driver_thread.should_report_aggregated_power()

    
    # Sim-spruce transactive boundary: 4 elements @ 4500, secondary-pump 80,
    # hp-ctrl-box 50, hp-odu 4300 -> 22430 W aggregate nameplate.
    hp_odu = layout.node(HSNN.hp_odu)
    assert hp_odu.NameplatePowerW == 4300
    assert driver_thread.nameplate_agg_power_w == 22_430
    power_reporting_threshold_ratio = driver_thread.async_power_reporting_threshold
    assert power_reporting_threshold_ratio == 0.02
    power_reporting_threshold_w = power_reporting_threshold_ratio * driver_thread.nameplate_agg_power_w
    assert power_reporting_threshold_w == pytest.approx(448.6)

    tt = layout.channel(HCN.hp_odu_pwr)
    driver_thread.latest_telemetry_value[tt] += 400
    assert not driver_thread.should_report_aggregated_power()
    driver_thread.latest_telemetry_value[tt] += 100
    assert driver_thread.should_report_aggregated_power()
    driver_thread.report_aggregated_power_w()
    assert driver_thread.latest_agg_power_w == 506

def meter_test_layout() -> HydronicLayout:
    settings = ScadaSettings()
    layout = load_layout(
        settings.paths.hardware_layout, Path(settings.paths.operational_params)
    )
    meter_component = layout.component_from_node(layout.node(CoreNodeNames.asset_power_meter))
    if not isinstance(meter_component, ElectricMeterComponent):
        raise TypeError(f"ERROR. Got meter component with wrong type ({type(meter_component)})")
    for config in meter_component.gt.ConfigList:
        layout.capture_tuning_by_channel[config.ChannelName].CapturePeriodS = 1
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
            h.child1.hardware_layout.data_channels[HCN.hp_odu_pwr],
            h.child1.hardware_layout.data_channels["hp-ctrl-box-pwr"],
            h.child1.hardware_layout.data_channels[HCN.secondary_pump_pwr],
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
#     """Verify that when a simulated change in power is generated, Scadd and Ltn both get a PowerWatts message"""
    async with ScadaLiveTest(
        request=request,
    ) as h:
        h.start_child1() # start primary scada
        h.start_parent() # start ltn
        scada = h.child1_app.scada


        data = scada.data
        print(f"type of h.child1_app.scada is {type(scada)}")
        ltn_received_counts = h.parent_to_child_stats.num_received_by_type
        initial = ltn_received_counts['power.watts']
        print(f"ltn has received {initial} power.watts messages")
        await h.await_for(
                lambda: data.latest_power_w is not None,
                "Scada wait for initial PowerWatts"
            )
        print(f"scada.data.latest_power_w is {data.latest_power_w}")

        p = typing.cast(
            PowerMeterDriverThread,
            h.child1_app.get_communicator_as_type(
                CoreNodeNames.asset_power_meter,
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

        transactive_channels = {
            data.layout.data_channels[name]
            for dc in data.layout.derived_channels.values()
            if dc.Strategy == "transactive-power"
            for name in dc.InputChannelNames
        }

        # Sim-spruce transactive boundary: the four elements, secondary-pump,
        # hp-ctrl-box, hp-odu.
        assert transactive_channels == {
            data.layout.data_channels[name]
            for name in (
                "buffer-top-elt-pwr", "buffer-bottom-elt-pwr",
                "tank1-top-elt-pwr", "tank1-bottom-elt-pwr",
                HCN.secondary_pump_pwr, "hp-ctrl-box-pwr", HCN.hp_odu_pwr,
            )
        }

        assert data.latest_channel_values["hp-ctrl-box-pwr"] == delta_w
        assert data.latest_channel_values[HCN.hp_odu_pwr] == delta_w

        # The sim driver applies fake_power_w to every metered channel, so
        # the aggregate sees all seven transactive channels move.
        assert data.latest_power_w == 7 * delta_w

        await h.await_for(
            lambda: ltn_received_counts['power.watts'] > initial,
            "Ltn wait for power.watts",
        )
        ltn = h.parent_app.ltn
        assert ltn.data.latest_power_w == 7 * delta_w


@pytest.mark.asyncio
async def test_whitewire_power_through_the_sim_meter_becomes_the_zone_heat_call(
    request: pytest.FixtureRequest,
) -> None:
    """House0 willow derives zone1-main-heat-call from zone1-main-whitewire-pwr
    (GreaterThanThreshold, 10 W), a channel the power meter captures."""
    config = Path(__file__).parent.parent / "config"
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = config / "gw.house0.willow.layout.json"
    settings.paths.operational_params = config / "gw.house0.willow.operational.params.json"
    async with ScadaLiveTest(request=request, child_app_settings=settings) as h:
        h.start_child1()
        data = h.child1_app.scada.data
        p = typing.cast(
            PowerMeterDriverThread,
            h.child1_app.get_communicator_as_type(
                CoreNodeNames.asset_power_meter, PowerMeter
            )._sync_thread,
        )
        assert {ch.Name for ch in p.derived_input_channels} == {"zone1-main-whitewire-pwr"}
        driver = typing.cast(GridworksSimPm1_PowerMeterDriver, p.driver)

        await h.await_for(
            lambda: data.latest_channel_values.get("zone1-main-heat-call") == 0,
            "heat call idle at 0 W",
        )
        driver.fake_power_w = 50
        await h.await_for(
            lambda: data.latest_channel_values.get("zone1-main-heat-call") == 1,
            "heat call calling at 50 W",
        )
        driver.fake_power_w = 0
        await h.await_for(
            lambda: data.latest_channel_values.get("zone1-main-heat-call") == 0,
            "heat call idle again at 0 W",
        )


WILLOW_LAYOUT = Path(__file__).parent.parent / "config" / "gw.house0.willow.layout.json"
WILLOW_OPS = Path(__file__).parent.parent / "config" / "gw.house0.willow.operational.params.json"
WHITEWIRE = "zone1-main-whitewire-pwr"


def willow_settings(lost_after_s: float) -> ScadaSettings:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = WILLOW_LAYOUT
    settings.paths.operational_params = WILLOW_OPS
    settings.power_meter_lost_after_s = lost_after_s
    return settings


def willow_layout_with_one_second_capture() -> HydronicLayout:
    layout = load_layout(WILLOW_LAYOUT, WILLOW_OPS)
    meter_component = layout.component_from_node(layout.node(CoreNodeNames.asset_power_meter))
    if not isinstance(meter_component, ElectricMeterComponent):
        raise TypeError(f"ERROR. Got meter component with wrong type ({type(meter_component)})")
    for config in meter_component.gt.ConfigList:
        layout.capture_tuning_by_channel[config.ChannelName].CapturePeriodS = 1
    return layout


def meter_thread(h: ScadaLiveTest) -> PowerMeterDriverThread:
    return typing.cast(
        PowerMeterDriverThread,
        h.child1_app.get_communicator_as_type(
            CoreNodeNames.asset_power_meter, PowerMeter
        )._sync_thread,
    )


def record_meter_messages(p: PowerMeterDriverThread) -> list[Message]:
    """Every message the driver thread queues from here on, still delivered."""
    sent: list[Message] = []
    deliver = p._put_to_async_queue

    def record_and_deliver(message: Message) -> None:
        sent.append(message)
        deliver(message)

    p._put_to_async_queue = record_and_deliver
    return sent


def flatlined_names(sent: list[Message]) -> list[str]:
    return [m.Payload.Channel.Name for m in sent if isinstance(m.Payload, ChannelFlatlined)]


@pytest.mark.asyncio
async def test_a_lost_meter_channel_goes_unknown_and_stops_reporting(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(
        request=request,
        child_app_settings=willow_settings(lost_after_s=1.0),
        child1_layout=willow_layout_with_one_second_capture(),
    ) as h:
        h.start_child1()
        data = h.child1_app.scada.data
        p = meter_thread(h)
        driver = typing.cast(GridworksSimPm1_PowerMeterDriver, p.driver)
        await h.await_for(
            lambda: data.latest_channel_values.get(HCN.hp_odu_pwr) is not None,
            "first hp-odu-pwr reading",
        )
        sent = record_meter_messages(p)
        driver.no_value_channel_names = {HCN.hp_odu_pwr}
        await h.await_for(
            lambda: data.latest_channel_values[HCN.hp_odu_pwr] is None,
            "hp-odu-pwr unknown at the scada",
        )
        received = len(data.recent_channel_values[HCN.hp_odu_pwr])
        others = len(data.recent_channel_values[HCN.hp_idu_pwr])
        await h.await_for(
            lambda: len(data.recent_channel_values[HCN.hp_idu_pwr]) >= others + 2,
            "two more capture periods on a live channel",
        )
        assert len(data.recent_channel_values[HCN.hp_odu_pwr]) == received
        assert data.latest_channel_values[HCN.hp_odu_pwr] is None
        assert flatlined_names(sent) == [HCN.hp_odu_pwr]


@pytest.mark.asyncio
async def test_a_short_gap_in_meter_reads_is_not_a_loss(
    request: pytest.FixtureRequest,
) -> None:
    lost_after_s = 3.0
    async with ScadaLiveTest(
        request=request,
        child_app_settings=willow_settings(lost_after_s=lost_after_s),
        child1_layout=willow_layout_with_one_second_capture(),
    ) as h:
        h.start_child1()
        data = h.child1_app.scada.data
        p = meter_thread(h)
        driver = typing.cast(GridworksSimPm1_PowerMeterDriver, p.driver)
        await h.await_for(
            lambda: data.latest_channel_values.get(HCN.hp_odu_pwr) == 0,
            "first hp-odu-pwr reading",
        )
        sent = record_meter_messages(p)
        # The watts move while the channel returns no value, so a value
        # that stays at 0 shows the reads in the gap came back empty.
        driver.no_value_channel_names = {HCN.hp_odu_pwr}
        driver.fake_power_w = 700
        await h.await_for(
            lambda: data.latest_channel_values[HCN.hp_idu_pwr] == 700,
            "a poll inside the gap",
        )
        assert data.latest_channel_values[HCN.hp_odu_pwr] == 0
        driver.no_value_channel_names = set()
        await h.await_for(
            lambda: data.latest_channel_values[HCN.hp_odu_pwr] == 700,
            "hp-odu-pwr read again",
        )
        await asyncio.sleep(lost_after_s + 1)
        assert flatlined_names(sent) == []
        assert data.latest_channel_values[HCN.hp_odu_pwr] == 700


@pytest.mark.asyncio
async def test_a_recovered_meter_channel_reports_on_that_poll(
    request: pytest.FixtureRequest,
) -> None:
    """The capture period stays at the layout's, so a report seconds after
    the first good read is the recovery and not the periodic beat."""
    async with ScadaLiveTest(
        request=request, child_app_settings=willow_settings(lost_after_s=1.0)
    ) as h:
        h.start_child1()
        data = h.child1_app.scada.data
        p = meter_thread(h)
        driver = typing.cast(GridworksSimPm1_PowerMeterDriver, p.driver)
        await h.await_for(
            lambda: data.latest_channel_values.get(WHITEWIRE) == 0,
            "first whitewire reading",
        )
        driver.no_value_channel_names = {WHITEWIRE}
        await h.await_for(
            lambda: data.latest_channel_values[WHITEWIRE] is None,
            "whitewire unknown at the scada",
        )
        sent = record_meter_messages(p)
        driver.no_value_channel_names = set()
        await h.await_for(
            lambda: data.latest_channel_values[WHITEWIRE] == 0,
            "whitewire back at the scada",
        )
        destinations = {
            m.Header.Dst
            for m in sent
            if isinstance(m.Payload, SyncedReadings)
            and WHITEWIRE in m.Payload.ChannelNameList
        }
        assert destinations == {CoreNodeNames.primary_scada, CoreNodeNames.derived_generator}


@pytest.mark.asyncio
async def test_a_recovered_transactive_channel_reports_aggregate_power(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(
        request=request, child_app_settings=willow_settings(lost_after_s=1.0)
    ) as h:
        h.start_child1()
        data = h.child1_app.scada.data
        p = meter_thread(h)
        driver = typing.cast(GridworksSimPm1_PowerMeterDriver, p.driver)
        assert HCN.hp_odu_pwr in p.transactive_channel_names
        await h.await_for(
            lambda: data.latest_channel_values.get(HCN.hp_odu_pwr) == 0,
            "first hp-odu-pwr reading",
        )
        driver.no_value_channel_names = {HCN.hp_odu_pwr}
        await h.await_for(
            lambda: data.latest_channel_values[HCN.hp_odu_pwr] is None,
            "hp-odu-pwr unknown at the scada",
        )
        sent = record_meter_messages(p)
        driver.no_value_channel_names = set()
        await h.await_for(
            lambda: data.latest_channel_values[HCN.hp_odu_pwr] == 0,
            "hp-odu-pwr back at the same watts",
        )
        assert [m.Payload.Watts for m in sent if isinstance(m.Payload, PowerWatts)] == [0]
