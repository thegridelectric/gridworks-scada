import datetime
from types import SimpleNamespace

from actors.scada import Scada
from gwadmin.watch.clients.relay_client import RelayConfig
from gwadmin.watch.clients.relay_client import RelayInfo
from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ActorClass
from gwsproto.enums import ChangeRelayPin
from gwsproto.enums import ChangeRelayState
from gwsproto.enums import TopState
from gwsproto.enums import TurnHpOnOff
from gwsproto.named_types import AdminDispatch
from gwsproto.named_types import FsmEvent
from gwsproto.named_types.scada_control_capabilities import ControlNode


class FakeAdminClient:
    def __init__(self) -> None:
        self.published: list[AdminDispatch] = []

    def publish(self, payload: AdminDispatch) -> None:
        self.published.append(payload)


class FakeCommunicator:
    def __init__(self, name: str) -> None:
        self.name = name
        self.messages = []

    def process_message(self, message) -> None:
        self.messages.append(message)


def test_control_node_handle_is_backward_compatible() -> None:
    node = ControlNode(Name=H0N.hp_scada_ops_relay, ActorClass=ActorClass.Relay)
    assert node.Handle is None


def test_relay_watch_client_uses_configured_control_handle() -> None:
    client = RelayWatchClient()
    admin_client = FakeAdminClient()
    client.set_admin_client(admin_client)
    client._relays = {
        H0N.hp_scada_ops_relay: RelayInfo(
                config=RelayConfig(
                    about_node_name=H0N.hp_scada_ops_relay,
                    handle=f"{H0N.admin}.{H0N.hp_boss}",
                    channel_name="hp-scada-ops-relay6",
                    event_type=ChangeRelayState.enum_name(),
                    energizing_event=ChangeRelayState.CloseRelay,
                    de_energizing_event=ChangeRelayState.OpenRelay,
                    energized_state="RelayClosed",
                deenergized_state="RelayOpen",
            )
        )
    }

    client._send_set_command(
        H0N.hp_scada_ops_relay,
        ChangeRelayPin.Energize,
        datetime.datetime(2026, 4, 20, 13, 18, 25),
        timeout_seconds=30,
    )

    assert len(admin_client.published) == 1
    dispatch = admin_client.published[0].DispatchTrigger
    assert dispatch.ToHandle == f"{H0N.admin}.{H0N.hp_boss}"
    assert dispatch.EventType == TurnHpOnOff.enum_name()
    assert dispatch.EventName == TurnHpOnOff.TurnOff


def test_scada_admin_dispatch_rewrites_hierarchical_relay_handles() -> None:
    admin_node = SimpleNamespace(name=H0N.admin, handle=H0N.admin)
    hp_boss_node = SimpleNamespace(
        name=H0N.hp_boss,
        handle=f"{H0N.admin}.{H0N.hp_boss}",
    )
    relay_node = SimpleNamespace(
        name=H0N.hp_scada_ops_relay,
        handle=f"{H0N.admin}.{H0N.hp_boss}.{H0N.hp_scada_ops_relay}",
    )

    relay_communicator = FakeCommunicator(H0N.hp_scada_ops_relay)

    class FakeLayout:
        def __init__(self) -> None:
            self._nodes = {
                admin_node.name: admin_node,
                hp_boss_node.name: hp_boss_node,
                relay_node.name: relay_node,
            }
            self._handles = {
                admin_node.handle: admin_node,
                hp_boss_node.handle: hp_boss_node,
                relay_node.handle: relay_node,
            }

        def node_by_handle(self, handle: str):
            return self._handles.get(handle)

        def node(self, name: str, default=None):
            return self._nodes.get(name, default)

        def boss_node(self, node):
            if node.name == relay_node.name:
                return hp_boss_node
            return admin_node

    class FakeScada:
        def __init__(self) -> None:
            self.admin = admin_node
            self.top_state = TopState.Auto
            self.layout = FakeLayout()
            self.timeout_seconds = None

        def admin_wakes_up(self) -> None:
            self.top_state = TopState.Admin

        def _renew_admin_timeout(self, timeout_seconds=None) -> None:
            self.timeout_seconds = timeout_seconds

        def log(self, _: str) -> None:
            pass

        def get_communicator(self, name: str):
            if name == relay_node.name:
                return relay_communicator
            return None

    scada = FakeScada()

    Scada.process_admin_dispatch(
        scada,
        admin_node,
        AdminDispatch(
            DispatchTrigger=FsmEvent(
                FromHandle=H0N.admin,
                ToHandle=f"{H0N.admin}.{H0N.hp_scada_ops_relay}",
                EventType=ChangeRelayState.enum_name(),
                EventName=ChangeRelayState.OpenRelay,
                SendTimeUnixMs=1776681505945,
                TriggerId="4262456a-57e2-4cf9-b071-f2b54766a2da",
            ),
            TimeoutSeconds=30,
        ),
    )

    assert scada.top_state == TopState.Admin
    assert scada.timeout_seconds == 30
    assert len(relay_communicator.messages) == 1

    forwarded_message = relay_communicator.messages[0]
    assert forwarded_message.Header.Src == H0N.hp_boss
    assert forwarded_message.Payload.FromHandle == hp_boss_node.handle
    assert forwarded_message.Payload.ToHandle == relay_node.handle
    assert forwarded_message.Payload.EventName == ChangeRelayState.OpenRelay
