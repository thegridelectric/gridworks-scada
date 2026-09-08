"""The admin seam on a Nolan layout, in-process on the sim fixture: the
control-capabilities projection the admin client keys everything off, and
an AdminAnalogDispatch in the admin TUI's wire shape reaching the
ZeroTenOutputer leaf through the scada's routing.

Both were bench failures on honeysuckle (2026-09-05): every admin link-up
logged `Trouble with SendLayout: 'NoneType' object has no attribute
'component'` (a House0 relay-multiplexer lookup on a Nolan layout), and a
forwarded dispatch produced no visible outputer activity."""

import time
import uuid
from pathlib import Path

import pytest

from actors.zero_ten_outputer import ZeroTenOutputer, code_from_volts_times_ten
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import (
    ActorClass,
    FiveVBossState,
    HpBossState,
    PicoCyclerState,
    RebootPicos,
    SinglePicoState,
    Turn5VOnOff,
    TurnHpOnOff,
)
from gwsproto.named_types import (
    AdminAnalogDispatch,
    AdminReleaseControl,
    AnalogDispatch,
    MachineStates,
    SingleMachineState,
)
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
DAC_NODE = "secondary-010v"
VOLTS_TIMES_TEN = 55


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def test_control_capabilities_on_nolan(app: ScadaApp) -> None:
    """A Nolan scada answers SendControlCapabilities with the cover of its
    tree: every relay and the 0-10V output are in the projection, hp-boss
    and five-v-boss are command-node rows with their own vocabulary
    (five-v-boss with two: the hold and the forwarded reboot),
    and the two relays they own (hp-scada-ops-relay, vdc-relay) carry no
    interface of their own."""
    scada = app.scada
    layout = scada.layout
    capabilities = scada.control_capabilities
    relay_names = {
        n.Name for n in layout.nodes.values() if n.ActorClass == ActorClass.Relay
    }
    assert {n.Name for n in capabilities.RelayNodes} == relay_names
    assert {n.Name for n in capabilities.DacNodes} == {DAC_NODE}
    assert {n.Name for n in capabilities.CommandNodes} == {H0N.hp_boss, H0N.five_v_boss, H0N.pico_cycler}
    assert {c.AboutNodeName for c in capabilities.ControlChannels} == relay_names | {
        DAC_NODE
    }
    interfaces = {i.ActorName: i for i in capabilities.CommandInterfaces}
    owned = {H0N.hp_scada_ops_relay, H0N.vdc_relay}
    assert set(interfaces) == (relay_names - owned) | {H0N.hp_boss, H0N.five_v_boss}
    hp_boss = interfaces[H0N.hp_boss]
    assert hp_boss.EventType == TurnHpOnOff.enum_name()
    assert hp_boss.StateType == HpBossState.enum_name()
    assert {(c.Event, c.ToState) for c in hp_boss.Commands} == {
        (TurnHpOnOff.TurnOn, HpBossState.HpOn),
        (TurnHpOnOff.TurnOff, HpBossState.HpOff),
    }
    five_v = {
        i.EventType: i for i in capabilities.CommandInterfaces if i.ActorName == H0N.five_v_boss
    }
    assert set(five_v) == {Turn5VOnOff.enum_name(), RebootPicos.enum_name()}
    assert [(c.Event, c.ToState) for c in five_v[Turn5VOnOff.enum_name()].Commands] == [
        (Turn5VOnOff.TurnOff, FiveVBossState.FiveVOff),
        (Turn5VOnOff.TurnOn, FiveVBossState.PicoCycler),
    ]
    assert [(c.Event, c.ToState) for c in five_v[RebootPicos.enum_name()].Commands] == [
        (RebootPicos.RebootPicos, FiveVBossState.PicoCycler)
    ]
    for name in relay_names - owned:
        config = next(
            c for c in layout.node(name).component.gt.ConfigList if c.ActorName == name
        )
        relay = interfaces[name]
        assert relay.EventType == config.EventType
        assert relay.StateType == config.StateType
        assert {(c.Event, c.ToState) for c in relay.Commands} == {
            (config.EnergizingEvent, config.EnergizedState),
            (config.DeEnergizingEvent, config.DeEnergizedState),
        }


def admin_dispatch(value: int) -> AdminAnalogDispatch:
    """The admin client's wire shape (gwadmin DACWatchClient._send_set_command)."""
    return AdminAnalogDispatch(
        Dispatch=AnalogDispatch(
            FromGNodeAlias=None,
            FromHandle=H0N.admin,
            ToHandle=f"{H0N.admin}.{DAC_NODE}",
            AboutName=DAC_NODE,
            Value=value,
            TriggerId=str(uuid.uuid4()),
            UnixTimeMs=int(time.time() * 1000),
        ),
        TimeoutSeconds=120,
    )


@pytest.mark.asyncio
async def test_admin_analog_dispatch_reaches_outputer(
    request: pytest.FixtureRequest,
) -> None:
    """On a running Nolan scada (the default test pair): admin wakes up, the
    tree is rewritten under admin, the dispatch lands in the outputer with
    ToHandle equal to its handle, and the sim chip write reports the level
    on the output's channel."""
    async with ScadaLiveTest(start_all=True, request=request) as h:
        await h.await_quiescent_connections()
        scada = h.child_app.scada
        out = h.child_app.proactor.get_communicator(DAC_NODE)
        assert isinstance(out, ZeroTenOutputer)
        expected_code = code_from_volts_times_ten(VOLTS_TIMES_TEN, out.config)
        scada.process_scada_message(scada.admin, admin_dispatch(VOLTS_TIMES_TEN))
        assert out.node.handle == f"{H0N.admin}.{DAC_NODE}"
        assert out.target_code == expected_code
        await h.await_for(
            lambda: scada.data.latest_channel_values.get(DAC_NODE) == VOLTS_TIMES_TEN,
            f"ERROR waiting for {DAC_NODE} to report {VOLTS_TIMES_TEN}",
        )
        scada.process_scada_message(scada.admin, AdminReleaseControl())


def test_cycler_state_reaches_admin_live(app: ScadaApp) -> None:
    """The pico-cycler reports its transitions as machine.states; the
    scada forwards the latest one to the admin link as the node's
    single.machine.state, so the panel's cycler row moves with the
    cycle rather than on the next snapshot. A roster row the cycler
    reports about a pico is not forwarded."""
    scada = app.scada
    scada.settings.admin.enabled = True
    sent: list = []
    scada._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    cycler = scada.layout.node(H0N.pico_cycler)
    now_ms = int(time.time() * 1000)
    scada.process_machine_states(
        cycler,
        MachineStates(
            MachineHandle=cycler.handle,
            StateEnum=PicoCyclerState.enum_name(),
            StateList=[PicoCyclerState.RelayOpening],
            UnixMsList=[now_ms],
        ),
    )
    forwarded = [p for dst, p in sent if dst == H0N.admin]
    assert len(forwarded) == 1
    assert isinstance(forwarded[0], SingleMachineState)
    assert forwarded[0].MachineHandle == cycler.handle
    assert forwarded[0].State == PicoCyclerState.RelayOpening
    assert forwarded[0].UnixMs == now_ms
    sent.clear()
    buffer = scada.layout.node("buffer")
    scada.process_machine_states(
        cycler,
        MachineStates(
            MachineHandle=buffer.handle,
            StateEnum=SinglePicoState.enum_name(),
            StateList=[SinglePicoState.Flatlined],
            UnixMsList=[now_ms],
        ),
    )
    assert [p for dst, p in sent if dst == H0N.admin] == []
