"""Admin turns the heat pump off and on through hp-boss on a running scada:
the admin package's own AdminClient over the test mosquitto, the scada
waking into Admin, hp-boss commanding the call relay at the relay's handle
under admin.hp-boss, the relay confirming at the (sim) pin, and LocalControl
back to Normal once admin releases. The in-process version is
test_hp_boss.py; this is the same drive over the wire."""

import time
import uuid
from pathlib import Path

import pytest
from gwadmin.config import (
    AdminConfig,
    AdminMQTTClient,
    CurrentAdminConfig,
    ScadaConfig,
)
from gwadmin.watch.clients.admin_client import AdminClient, AdminClientCallbacks
from gwproactor.config.mqtt import TLSInfo

from actors.config import AdminLinkSettings
from actors.hp_boss import HpBoss
from actors.local_control_loader import LocalControl
from actors.relay import Relay
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import HpBossState, LocalControlTopState, TopState, TurnHpOnOff
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, FsmEvent
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    # The House0 pairs are off until the sieg loop has been exercised: their
    # TurnOn leg waits on a SiegLoopReady from the sieg-loop actor, which has
    # never run unsupervised, so admin's TurnOn would sit in PreparingToTurnOn
    # for TURN_ON_ANYWAY_S. Uncomment with the sieg refactor.
    # "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
    # "house0-sim": (
    #     "gw.house0.sim.layout.json",
    #     "gw.house0.sim.operational.params.json",
    # ),
}
SCADA_SHORT_NAME = "hp-boss-live"


def admin_turn(name: TurnHpOnOff) -> AdminDispatch:
    """The admin client's wire shape for the hp-boss dispatch."""
    return AdminDispatch(
        DispatchTrigger=FsmEvent(
            FromHandle=H0N.admin,
            ToHandle=f"{H0N.admin}.{H0N.hp_boss}",
            EventType=TurnHpOnOff.enum_name(),
            EventName=name,
            SendTimeUnixMs=int(time.time() * 1000),
            TriggerId=str(uuid.uuid4()),
        ),
        TimeoutSeconds=120,
    )


class AdminSide:
    """The admin client against the test broker, with its link state."""

    def __init__(self, scada_long_name: str, admin_link: AdminLinkSettings) -> None:
        self.mqtt_state = ""
        self.client = AdminClient(
            CurrentAdminConfig(
                config=AdminConfig(
                    scadas={
                        SCADA_SHORT_NAME: ScadaConfig(
                            long_name=scada_long_name,
                            mqtt=AdminMQTTClient(
                                host=admin_link.host,
                                port=admin_link.port,
                                tls=TLSInfo(use_tls=False),
                            ),
                        )
                    }
                ),
                curr_scada=SCADA_SHORT_NAME,
            ),
            AdminClientCallbacks(mqtt_state_change_callback=self.on_state),
        )

    def on_state(self, old: str, new: str) -> None:
        self.mqtt_state = new


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", sorted(PAIRS))
async def test_admin_turns_heat_pump_on_and_off_through_hp_boss_live(
    pair: str, request: pytest.FixtureRequest
) -> None:
    layout, ops = PAIRS[pair]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.admin = AdminLinkSettings(enabled=True, tls=TLSInfo(use_tls=False))
    async with ScadaLiveTest(
        start_all=True, request=request, child_app_settings=settings
    ) as h:
        await h.await_quiescent_connections()
        scada = h.child_app.scada
        hp_boss = h.child_app.proactor.get_communicator(H0N.hp_boss)
        assert isinstance(hp_boss, HpBoss)
        relay = h.child_app.proactor.get_communicator(H0N.hp_scada_ops_relay)
        assert isinstance(relay, Relay)
        lc = h.child_app.proactor.get_communicator(H0N.local_control)
        assert isinstance(lc, LocalControl)
        relay_cfg = relay.relay_actor_config
        hp_boss_handle = f"{H0N.admin}.{H0N.hp_boss}"
        relay_handle = f"{hp_boss_handle}.{H0N.hp_scada_ops_relay}"

        admin = AdminSide(scada.layout.scada_g_node_alias, settings.admin)
        admin.client.start()
        try:
            await h.await_for(
                lambda: admin.mqtt_state == "active",
                "ERROR waiting for the admin client's link to go active",
            )

            admin.client.publish(admin_turn(TurnHpOnOff.TurnOff))
            await h.await_for(
                lambda: scada.top_state == TopState.Admin,
                "ERROR waiting for the scada to wake into Admin",
            )
            assert lc.top_state == LocalControlTopState.Dormant
            assert hp_boss.node.handle == hp_boss_handle
            assert relay.node.handle == relay_handle
            await h.await_for(
                lambda: hp_boss.state == HpBossState.HpOff,
                "ERROR waiting for hp-boss to reach HpOff",
            )
            await h.await_for(
                lambda: relay.state == relay_cfg.DeEnergizedState,
                "ERROR waiting for the call relay to confirm open",
            )
            # The relay ignores a command from anyone but its handle parent
            # (bad_boss), so a state change at this handle came from hp-boss.

            admin.client.publish(admin_turn(TurnHpOnOff.TurnOn))
            await h.await_for(
                lambda: hp_boss.state == HpBossState.HpOn,
                "ERROR waiting for hp-boss to reach HpOn",
            )
            await h.await_for(
                lambda: relay.state == relay_cfg.EnergizedState,
                "ERROR waiting for the call relay to confirm closed",
            )

            admin.client.publish(AdminReleaseControl())
            await h.await_for(
                lambda: scada.top_state == TopState.Auto,
                "ERROR waiting for admin's release to reach the scada",
            )
            assert lc.top_state == LocalControlTopState.Normal
        finally:
            admin.client.stop()
