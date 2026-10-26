"""Subscriptions, in-process on the sim Nolan fixture: an actor asks the
scada for a channel's readings or a node's machine states, and the scada
forwards them as they arrive."""

import time
from pathlib import Path

import pytest

from actors.in_process_messages import ChannelSubscribe, MachineStateSubscribe
from gwsproto.enums import HpBossState
from gwsproto.named_types import (
    ChannelFlatlined,
    SingleMachineState,
    SingleReading,
    SyncedReadings,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
HP_ODU_PWR = "hp-odu-pwr"
PRIMARY_PUMP_PWR = "primary-pump-pwr"
HP_WATCH = "hp-watch"


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def capture_sends(scada) -> list:
    sent: list = []
    scada._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def test_a_single_reading_reaches_each_subscriber_and_no_one_else(app: ScadaApp) -> None:
    """A SingleReading on a subscribed channel goes to every subscriber as
    a SingleReading; a reading on a channel nobody subscribed to goes to
    none."""
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    local_control = scada.layout.node(CoreNodeNames.local_control)
    meter = scada.layout.node(CoreNodeNames.asset_power_meter)
    scada.process_scada_message(hp_watch, ChannelSubscribe(ChannelName=HP_ODU_PWR))
    scada.process_scada_message(local_control, ChannelSubscribe(ChannelName=HP_ODU_PWR))
    sent = capture_sends(scada)
    now_ms = int(time.time() * 1000)

    reading = SingleReading(ChannelName=HP_ODU_PWR, Value=640, ScadaReadTimeUnixMs=now_ms)
    scada.process_scada_message(meter, reading)
    forwarded = [(dst, p) for dst, p in sent if isinstance(p, SingleReading)]
    assert forwarded == [(HP_WATCH, reading), (CoreNodeNames.local_control, reading)]

    sent.clear()
    scada.process_scada_message(
        meter,
        SingleReading(ChannelName=PRIMARY_PUMP_PWR, Value=40, ScadaReadTimeUnixMs=now_ms),
    )
    assert [dst for dst, p in sent if dst in (HP_WATCH, CoreNodeNames.local_control)] == []


def test_a_synced_reading_reaches_the_subscriber_as_a_single_reading(app: ScadaApp) -> None:
    """The power meter reports its channels together; the subscriber gets
    its own channel's value as a SingleReading carrying the message's read
    time, and nothing for the other channels."""
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    meter = scada.layout.node(CoreNodeNames.asset_power_meter)
    scada.process_scada_message(hp_watch, ChannelSubscribe(ChannelName=HP_ODU_PWR))
    sent = capture_sends(scada)
    now_ms = int(time.time() * 1000)

    scada.process_scada_message(
        meter,
        SyncedReadings(
            ChannelNameList=[PRIMARY_PUMP_PWR, HP_ODU_PWR],
            ValueList=[40, 640],
            ScadaReadTimeUnixMs=now_ms,
        ),
    )
    assert [p for dst, p in sent if dst == HP_WATCH] == [
        SingleReading(ChannelName=HP_ODU_PWR, Value=640, ScadaReadTimeUnixMs=now_ms)
    ]


def test_a_flatline_reaches_the_channels_subscribers(app: ScadaApp) -> None:
    """A ChannelFlatlined for a subscribed channel goes to its subscribers
    as received; one for another channel does not."""
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    meter = scada.layout.node(CoreNodeNames.asset_power_meter)
    scada.process_scada_message(hp_watch, ChannelSubscribe(ChannelName=HP_ODU_PWR))
    sent = capture_sends(scada)

    flatlined = ChannelFlatlined(
        FromName=meter.name, Channel=scada.layout.data_channels[HP_ODU_PWR]
    )
    scada.process_scada_message(meter, flatlined)
    scada.process_scada_message(
        meter,
        ChannelFlatlined(
            FromName=meter.name,
            Channel=scada.layout.data_channels[PRIMARY_PUMP_PWR],
        ),
    )
    assert [p for dst, p in sent if dst == HP_WATCH] == [flatlined]


def test_subscribing_twice_forwards_once(app: ScadaApp) -> None:
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    meter = scada.layout.node(CoreNodeNames.asset_power_meter)
    scada.process_scada_message(hp_watch, ChannelSubscribe(ChannelName=HP_ODU_PWR))
    scada.process_scada_message(hp_watch, ChannelSubscribe(ChannelName=HP_ODU_PWR))
    sent = capture_sends(scada)

    scada.process_scada_message(
        meter,
        SingleReading(
            ChannelName=HP_ODU_PWR, Value=640, ScadaReadTimeUnixMs=int(time.time() * 1000)
        ),
    )
    assert len([p for dst, p in sent if dst == HP_WATCH]) == 1


def test_a_subscription_to_a_channel_the_layout_lacks_raises(app: ScadaApp) -> None:
    """A subscription to nothing is a defect in the subscriber: the scada
    raises rather than logging it."""
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    with pytest.raises(ValueError, match="no-such-channel"):
        scada.process_scada_message(hp_watch, ChannelSubscribe(ChannelName="no-such-channel"))
    assert scada.channel_subscribers == {}


def hp_boss_state(handle: str, state: HpBossState) -> SingleMachineState:
    return SingleMachineState(
        MachineHandle=handle,
        StateEnum=HpBossState.enum_name(),
        State=state,
        UnixMs=int(time.time() * 1000),
    )


def test_a_machine_state_reaches_its_subscribers_under_every_tree(app: ScadaApp) -> None:
    """A subscription names the node, so the states keep arriving when the
    command tree changes hands and the machine's handle moves with it."""
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    hp_boss = scada.layout.node(HSNN.hp_boss)
    scada.process_scada_message(hp_watch, MachineStateSubscribe(NodeName=hp_boss.name))
    sent = capture_sends(scada)

    under_auto = hp_boss_state(hp_boss.handle, HpBossState.HpOn)
    scada.process_scada_message(hp_boss, under_auto)
    under_admin = hp_boss_state(f"{CoreNodeNames.admin}.{hp_boss.name}", HpBossState.HpOff)
    scada.process_scada_message(hp_boss, under_admin)
    assert [p for dst, p in sent if dst == HP_WATCH] == [under_auto, under_admin]


def test_a_late_machine_state_subscriber_gets_the_latest_state(app: ScadaApp) -> None:
    """A subscriber that starts after the publisher's boot report is sent
    the state the scada holds; one that subscribes before any report is
    sent nothing until the first arrives."""
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    local_control = scada.layout.node(CoreNodeNames.local_control)
    hp_boss = scada.layout.node(HSNN.hp_boss)
    scada._data.latest_machine_state.pop(hp_boss.name, None)
    sent = capture_sends(scada)

    scada.process_scada_message(hp_watch, MachineStateSubscribe(NodeName=hp_boss.name))
    assert [p for dst, p in sent if dst == HP_WATCH] == []

    state = hp_boss_state(hp_boss.handle, HpBossState.HpOn)
    scada.process_scada_message(hp_boss, state)
    scada.process_scada_message(local_control, MachineStateSubscribe(NodeName=hp_boss.name))
    assert [p for dst, p in sent if dst == CoreNodeNames.local_control] == [state]


def test_a_subscription_to_a_node_the_layout_lacks_raises(app: ScadaApp) -> None:
    scada = app.scada
    hp_watch = scada.layout.node(HP_WATCH)
    with pytest.raises(ValueError, match="no-such-node"):
        scada.process_scada_message(hp_watch, MachineStateSubscribe(NodeName="no-such-node"))
    assert scada.machine_state_subscribers == {}
