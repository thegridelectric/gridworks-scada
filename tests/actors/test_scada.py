"""Test Scada"""
import logging
import time

from gwproactor_test.certs import uses_tls
from gwproactor_test.certs import copy_keys

import pytest
from scada_app import ScadaApp
from actors.config import ScadaSettings
from gwsproto.named_types import ChannelReadings, ReportEvent, SnapshotSpaceheat
from gwsproto.data_classes.house_0_names import H0N, H0CN
from tests.utils.scada_live_test_helper import ScadaLiveTest


def test_scada_small():
    scada_app = ScadaApp(app_settings=ScadaSettings(is_simulated=True))
    settings = scada_app.settings
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.mkdirs()
    scada_app.instantiate()
    layout = scada_app.hardware_layout
    scada = scada_app.scada
    assert layout.power_meter_node == layout.node(H0N.primary_power_meter)
    channel_names = [ch.Name for ch in scada._data.my_channels]
    assert (
        list(scada._data.latest_channel_values.keys())
        == channel_names
    )
    assert (
        list(scada._data.recent_channel_values.keys())
        == channel_names
    )
    assert (
        list(scada._data.recent_channel_unix_ms.keys())
        == channel_names
    )

    assert scada.layout.vdc_relay.name == H0N.vdc_relay

    ###########################################
    # Testing making report events
    ###########################################

    ch = scada._layout.data_channels[H0CN.store_pump_pwr]

    scada._data.recent_channel_values[ch.Name] = [43]
    scada._data.recent_channel_unix_ms[ch.Name] = [
        int(time.time() * 1000)
    ]
    
    s = scada._data.make_channel_readings(ch=ch)
    assert isinstance(s, ChannelReadings)


    scada.send_report()

    # ##################################
    # # Testing actuation
    # ##################################

    # # test that turn_on and turn_off only work for boolean actuator nodes

    # result = scada.turn_on(meter_node)
    # assert result == ScadaCmdDiagnostic.DISPATCH_NODE_NOT_RELAY
    # result = scada.turn_off(meter_node)
    # assert result == ScadaCmdDiagnostic.DISPATCH_NODE_NOT_RELAY

    #################################
    # Other SCADA small tests
    ##################################

    scada._last_report_second = int(time.time() - 400)
    assert scada.time_to_send_report() is True


@pytest.mark.asyncio
async def test_show_types(request: pytest.FixtureRequest):
    """Verify scada periodic status and snapshot"""
    async with ScadaLiveTest(
        start_all=True,
        request=request,
    ) as h:
        await h.await_quiescent_connections()
        print("LiveTest", type(h))
        print("child", type(h.child))
        print("child_app", type(h.child_app))
        print("prime_actor", type(h.child_app.prime_actor))
        print("link", type(h.child_to_parent_link))
        print("link stats", type(h.child_to_parent_stats))
        print("child stats", type(h.child.stats))


@pytest.mark.asyncio
async def test_scada_periodic_report_delivery(request: pytest.FixtureRequest):
    """Verify scada periodic status and snapshot"""

    async with ScadaLiveTest(
        start_all=True,
        child_app_settings=ScadaSettings(seconds_per_report=1),
        request=request,
    ) as h:
        msg_type = ReportEvent.model_fields["TypeName"].default
        # Note: for sanity get the *link* stats, not the global stats.
        # the globals stats *might* work in this case.
        ltn_received_counts = h.parent_to_child_stats.num_received_by_type
        initial_count = ltn_received_counts[msg_type]
        await h.await_for(
            lambda: ltn_received_counts[msg_type] > initial_count,
            f"ERROR waiting for LTN to receive > {initial_count} reports",
        )
        # print(h.summary_str())

@pytest.mark.asyncio
async def test_scada_periodic_snapshot_delivery(request: pytest.FixtureRequest):
    """Verify scada periodic status and snapshot"""

    async with ScadaLiveTest(
        start_all=True,
        child_app_settings=ScadaSettings(seconds_per_snapshot=1),
        request=request,
    ) as h:
        msg_type = SnapshotSpaceheat.model_fields["TypeName"].default
        ltn_received_counts = h.parent_to_child_stats.num_received_by_type
        initial_count = ltn_received_counts[msg_type]
        await h.await_for(
            lambda: ltn_received_counts[msg_type] > initial_count,
            f"ERROR waiting for LTN to receive > {initial_count} snapshots"
        )



@pytest.mark.asyncio
async def test_scada_snaphot_request_delivery(request: pytest.FixtureRequest):
    """Verify scada sends snapshot upon request from Ltn"""
    async with ScadaLiveTest(
            start_all=True,
            child_app_settings=ScadaSettings(seconds_per_snapshot=100000000),
            request=request,
    ) as h:
        await h.await_quiescent_connections()
        h.child.delimit("Sending snapshot request", log_level=logging.WARNING)
        ltn_receive_counts = h.parent_to_child_stats.num_received_by_type
        snap_type = SnapshotSpaceheat.model_fields["TypeName"].default
        initital_snapshots = ltn_receive_counts[snap_type]
        h.parent_app.prime_actor.snap()
        await h.await_for(
            lambda: ltn_receive_counts[snap_type] > initital_snapshots,
            f"ERROR waiting for LTN to receice > {initital_snapshots} snapshots"
        )

# @pytest.mark.skip(reason="Skipping for now")
# @pytest.mark.asyncio
# async def test_scada_report_content_dynamics(tmp_path, monkeypatch, request):
#
#     monkeypatch.chdir(tmp_path)
#     settings = ScadaSettings(seconds_per_report=1)
#     if uses_tls(settings):
#         copy_keys("scada", settings)
#     settings.paths.mkdirs(parents=True)
#     layout = House0Layout.load(settings.paths.hardware_layout)
#     actors = Actors(
#         settings,
#         layout=layout,
#         scada=ScadaRecorder(H0N.primary_scada, settings, hardware_layout=layout),
#         ltn_settings=AsyncFragmentRunner.make_ltn_settings()
#     )
#     actors.scada._last_status_second = int(time.time())
#     actors.scada.suppress_report = True
#
#     class Fragment(ProtocolFragment):
#
#         def get_requested_proactors(self):
#             return [self.runner.actors.scada, self.runner.actors.ltn]
#
#         async def async_run(self):
#             ltn = self.runner.actors.ltn
#             scada = self.runner.actors.scada
#             link_stats = scada.stats.links["gridworks"]
#             meter = self.runner.actors.meter
#             meter_telemetry_message_type = "synced.readings"
#
#             # Verify scada status and snapshot are emtpy
#             report = scada._data.make_report(int(time.time()))
#             snapshot = scada._data.make_snapshot()
#             assert len(report.ChannelReadingList) == 0
#             assert len(snapshot.LatestReadingList) == 0
#             assert link_stats.num_received_by_type[meter_telemetry_message_type] == 0
#
#             # Make sub-actors send their reports
#             for actor in [meter]:
#                 scada.add_communicator(actor)
#                 actor.start()
#             await await_for(
#                 scada._links.link(scada.GRIDWORKS_MQTT).active,
#                 10,
#                 "ERROR waiting link active",
#                 err_str_f=scada.summary_str
#             )
#             assert scada.scada_ltn_fast_dispatch_contract_is_alive
#
#             # Provoke a message by increasing the power of hp-odu
#             hp_odu = scada._data.hardware_layout.node(H0N.hp_odu)
#             assert hp_odu is not None
#             scada._layout.channel
#             ch = scada._layout.channel(H0CN.hp_odu_pwr)
#             meter._sync_thread.latest_telemetry_value[ch] += 300
#
#             await await_for(
#                 lambda: (
#                     scada.stats.num_received_by_type[meter_telemetry_message_type] >= 1
#                 ),
#                 5,
#                 "Scada wait for reports",
#                 err_str_f=scada.summary_str
#             )
#
#             report = scada._data.make_report(int(time.time()))
#             NUM_POWER_CHANNELS = 3
#             assert len(report.ChannelReadingList) == NUM_POWER_CHANNELS
#
#
#             # Cause scada to send a report (and snapshot) now
#             scada.suppress_report = False
#
#             # Verify Ltn got status and snapshot
#             await await_for(
#                 lambda: ltn.stats.num_received_by_type[ReportEvent.model_fields["TypeName"].default] == 1,
#                 5,
#                 "Ltn wait for status message",
#                 err_str_f=ltn.summary_str
#             )
#             # await await_for(
#             #     lambda: ltn.stats.num_received_by_type[SnapshotSpaceheat.model_fields["TypeName"].default] == 1,
#             #     5,
#             #     "Ltn wait for snapshot message",
#             #     err_str_f=ltn.summary_str
#             # )
#
#             # Verify contents of status and snapshot are as expected
#             report = ltn.data.latest_report
#             assert isinstance(report, Report)
#             print(report.ChannelReadingList)
#             assert len(report.ChannelReadingList) == NUM_POWER_CHANNELS
#             # snapshot = ltn.data.latest_snapshot
#             # assert isinstance(snapshot, SnapshotSpaceheat)
#
#             # I don't understand why this is 0
#             # assert len(snapshot.LatestReadingList) ==  1
#
#
#             # Turn off telemtry reporting
#             for actor in [meter]:
#                 actor.stop()
#             for actor in [meter]:
#                 await actor.join()
#             # Wait for scada to send at least one more status.
#             reports_received = ltn.stats.total_received(ReportEvent.model_fields["TypeName"].default)
#             await await_for(
#                 lambda: ltn.stats.total_received(ReportEvent.model_fields["TypeName"].default) > reports_received,
#                 5,
#                 "Ltn wait for status message 2",
#                 err_str_f=ltn.summary_str
#             )
#
#             # Verify scada has cleared its state
#             report = scada._data.make_report(int(time.time()))
#             assert len(report.ChannelReadingList) == 0
#
#
#     runner = AsyncFragmentRunner(settings, actors=actors, tag=request.node.name)
#     runner.add_fragment(Fragment(runner))
#     await runner.async_run()
