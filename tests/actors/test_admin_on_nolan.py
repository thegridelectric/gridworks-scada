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
from gwsproto.enums import ActorClass
from gwsproto.named_types import (
    AdminAnalogDispatch,
    AdminReleaseControl,
    AnalogDispatch,
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "scada.control.capabilities/001 requires the House0 Krida "
        "I2cRelayComponent; a Nolan layout cannot emit it until the word drops it"
    ),
)
def test_control_capabilities_on_nolan(app: ScadaApp) -> None:
    """A Nolan scada answers SendControlCapabilities: every relay and the
    0-10V output are in the projection, keyed off the layout's actuator
    surface rather than a House0 node name."""
    scada = app.scada
    layout = scada.layout
    capabilities = scada.control_capabilities
    relay_names = {
        n.Name for n in layout.nodes.values() if n.ActorClass == ActorClass.Relay
    }
    assert {n.Name for n in capabilities.RelayNodes} == relay_names
    assert {n.Name for n in capabilities.DacNodes} == {DAC_NODE}
    assert {c.AboutNodeName for c in capabilities.ControlChannels} == relay_names | {
        DAC_NODE
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
