"""The rolling distribution energy when scada2 reads the distribution
temperatures. A capturer the primary scada runs posts its readings to the
derived generator itself (the power meter does, for dist-flow). A capturer
on scada2 cannot reach it: scada2 forwards every synced reading to the
primary, and the primary posts the ones that feed a derived channel on to
the generator. The sim House0 pairs read dist-swt and dist-rwt on the
primary, so this test re-parents those two sensors under scada2, as the
installed houses have them. Found on oak, which reported 0 Wh all day."""

from pathlib import Path

from actors.derived_generator import DerivedGenerator
from actors.scada import Scada
from clock import ManualClock
from gwproto.message import Message
from gwsproto.named_types import SingleReading, SyncedReadings
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
START_S = 1_767_625_200  # 2026-01-05 10:00 EST
START_MS = START_S * 1000


def orange_on_a_manual_clock() -> tuple[ScadaApp, ManualClock]:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.house0.orange.layout.json"
    settings.paths.operational_params = CONFIG / "gw.house0.orange.operational.params.json"
    settings.paths.mkdirs()
    clock = ManualClock(start_s=START_S)
    app = ScadaApp(app_settings=settings, clock=clock)
    app.instantiate()
    return app, clock


def read_on_scada2(scada: Scada, channel_names: list[str]) -> None:
    """Move each channel's sensor node under scada2 in the loaded layout."""
    for name in channel_names:
        node = scada.layout.data_channels[name].captured_by_node
        node.ActorHierarchyName = f"{CoreNodeNames.secondary_scada}.{node.Name}"
        assert scada.layout.parent_node(node) is scada.layout.node(CoreNodeNames.secondary_scada)


def route_scada_sends(scada: Scada, generator: DerivedGenerator) -> list[tuple[str, object]]:
    """Record what the primary scada sends and deliver the generator's share."""
    sent: list[tuple[str, object]] = []

    def send(to_node, payload, from_node=None) -> None:
        sent.append((to_node.Name, payload))
        if to_node.Name == generator.name:
            src = from_node.Name if from_node is not None else scada.name
            generator.process_message(Message(Src=src, Dst=generator.name, Payload=payload))

    scada._send_to = send
    return sent


def test_dist_temps_read_on_scada2_reach_the_rolling_dist_energy() -> None:
    app, clock = orange_on_a_manual_clock()
    scada = app.scada
    generator = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert generator is not None
    read_on_scada2(scada, [HCN.dist_swt, HCN.dist_rwt])
    scada_sent = route_scada_sends(scada, generator)
    emitted: list[tuple[str, object]] = []
    generator._send_to = lambda dst, payload, src=None: emitted.append((dst.Name, payload))

    # scada2 forwards the two temperatures it read: 45 C out, 35 C back.
    scada.process_synced_readings(
        scada.layout.node(CoreNodeNames.secondary_scada),
        SyncedReadings(
            ChannelNameList=[HCN.dist_swt, HCN.dist_rwt],
            ValueList=[4500, 3500],
            ScadaReadTimeUnixMs=START_MS,
        ),
    )
    forwarded = [p for dst, p in scada_sent if dst == generator.name]
    assert {p.ChannelName for p in forwarded if isinstance(p, SingleReading)} == {HCN.dist_swt, HCN.dist_rwt}

    # The power meter posts dist-flow to the generator itself: 5 gpm.
    generator.process_message(
        Message(
            Src=CoreNodeNames.asset_power_meter,
            Dst=generator.name,
            Payload=SyncedReadings(
                ChannelNameList=[HCN.dist_flow], ValueList=[500], ScadaReadTimeUnixMs=START_MS
            ),
        )
    )

    clock.advance(62 * 60)
    [dc] = generator.rolling_dist_energy_channels
    generator.tick_rolling_dist_energy(dc)

    [energy] = [p for _, p in emitted if isinstance(p, SingleReading) and p.ChannelName == dc.Name]
    # 5 gpm at a 10 K drop is about 13 kW, so about 13 kWh over the hour.
    assert 11_000 < energy.Value < 15_000


def test_dist_temps_read_on_the_primary_are_not_forwarded_twice() -> None:
    """A capturer the primary runs posts to the generator itself; the scada
    must not post the same reading again."""
    app, _ = orange_on_a_manual_clock()
    scada = app.scada
    generator = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert generator is not None
    scada_sent = route_scada_sends(scada, generator)
    scada.process_synced_readings(
        scada.layout.node(HCN.dist_swt),
        SyncedReadings(ChannelNameList=[HCN.dist_swt], ValueList=[4500], ScadaReadTimeUnixMs=START_MS),
    )
    assert not [p for dst, p in scada_sent if dst == generator.name]
