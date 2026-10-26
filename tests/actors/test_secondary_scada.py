"""scada2 re-sends the latest reading of every channel it has forwarded each
time its link to the scada goes active, with the original read times, so a
scada that restarts or drops the link holds scada2's channels within a second
of the link coming back rather than waiting a capture period."""

import time

import pytest
from gwproto.message import Message

from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.named_types import SyncedReadings
from tests.utils.scada_live_test_helper import ScadaLiveTest


@pytest.mark.asyncio
async def test_scada2_resends_readings_when_link_goes_active(
    request: pytest.FixtureRequest,
) -> None:
    async with ScadaLiveTest(start_all=True, request=request) as h:
        await h.await_for(
            lambda: h.child1_to_child2_link.active()
            and h.child2_to_child1_link.active(),
            "ERROR waiting for the scada and scada2 to connect",
        )
        scada = h.child1_app.scada
        scada2 = h.child2_app.prime_actor
        read_time_ms = int(time.time() * 1000) - 20_000

        def from_scada2(channel: str) -> list[int]:
            """The values the scada holds for the channel that carry scada2's
            read time. The scada's own simulated BTU meter reports the same
            channels, at its own read times."""
            data = scada._data
            return [
                value
                for value, read_ms in zip(
                    data.recent_channel_values[channel],
                    data.recent_channel_unix_ms[channel],
                )
                if read_ms == read_time_ms
            ]
        readings = SyncedReadings(
            ChannelNameList=[HCN.hp_lwt, HCN.hp_ewt],
            ValueList=[96_000, 91_000],
            ScadaReadTimeUnixMs=read_time_ms,
        )
        scada2.services.send_threadsafe(
            Message(
                Src=scada2.node.name,
                Dst=CoreNodeNames.primary_scada,
                Payload=readings,
            )
        )
        await h.await_for(
            lambda: scada._data.latest_channel_unix_ms[HCN.hp_lwt] == read_time_ms
            and scada._data.latest_channel_unix_ms[HCN.hp_ewt] == read_time_ms,
            "ERROR waiting for the scada to take scada2's first report",
        )
        assert from_scada2(HCN.hp_lwt) == [96_000]
        assert from_scada2(HCN.hp_ewt) == [91_000]

        h.child2.force_mqtt_disconnect(h.child2.upstream_client)
        await h.await_for(
            lambda: not h.child2_to_child1_link.active(),
            "ERROR waiting for scada2's link to the scada to drop",
        )
        await h.await_for(
            lambda: h.child2_to_child1_link.active(),
            "ERROR waiting for scada2's link to the scada to come back",
        )
        await h.await_for(
            lambda: len(from_scada2(HCN.hp_lwt)) == 2
            and len(from_scada2(HCN.hp_ewt)) == 2,
            "ERROR waiting for scada2 to re-send its readings",
            timeout=1.0,
        )
        assert from_scada2(HCN.hp_lwt) == [96_000] * 2
        assert from_scada2(HCN.hp_ewt) == [91_000] * 2
