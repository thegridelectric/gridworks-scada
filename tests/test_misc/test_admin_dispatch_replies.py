"""gwadmin hears the scada's answer to a dispatch. The relay client remembers
each command it publishes by TriggerId; an ack or nack arriving on the admin
link is paired with that command and handed to the panel's callback with the
reason, so a refused command is seen instead of silent."""

import time
import uuid

from gwproto import Message as GWMessage
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ActorClass, ScadaCmdRefusalReason, PicoCyclerState, RebootPicos
from gwsproto.named_types import (
    AdminDispatch,
    DispatchAck,
    DispatchNack,
    CommandInterface,
    CommandTransition,
    ScadaControlCapabilities,
    SingleReading,
    SpaceheatNodeGt,
)

from gwadmin.watch.clients.dispatch_replies import DispatchReply
from gwadmin.watch.clients.relay_client import RelayClientCallbacks, RelayWatchClient


class CapturingAdminClient:
    def __init__(self) -> None:
        self.published: list = []

    def publish(self, payload) -> None:
        self.published.append(payload)

    def started(self) -> bool:
        return False


def scada_message(payload) -> tuple[str, bytes]:
    message = GWMessage(Src="scada", Dst=H0N.admin, Payload=payload)
    return message.mqtt_topic(), message.model_dump_json().encode()


def cycler_capabilities() -> ScadaControlCapabilities:
    """The smallest cover with a pico-cycler row: one command node under admin."""
    return ScadaControlCapabilities(
        FromGNodeAlias="d1.isone.me.versant.keene.beech.scada",
        MessageCreatedMs=int(time.time() * 1000),
        RelayNodes=[],
        DacNodes=[],
        CommandNodes=[
            SpaceheatNodeGt(
                Name=H0N.pico_cycler,
                ActorHierarchyName=f"s.{H0N.pico_cycler}",
                Handle=f"{H0N.admin}.{H0N.pico_cycler}",
                ActorClass=ActorClass.PicoCycler,
                ShNodeId=str(uuid.uuid4()),
            )
        ],
        ControlChannels=[],
        CommandInterfaces=[
            CommandInterface(
                ActorName=H0N.pico_cycler,
                EventType=RebootPicos.enum_name(),
                StateType=PicoCyclerState.enum_name(),
                Commands=[
                    CommandTransition(
                        Event=RebootPicos.RebootPicos, ToState=PicoCyclerState.RelayOpening
                    )
                ],
            )
        ],
    )


def client_with_replies() -> tuple[RelayWatchClient, CapturingAdminClient, list[DispatchReply]]:
    replies: list[DispatchReply] = []
    client = RelayWatchClient(callbacks=RelayClientCallbacks(dispatch_reply_callback=replies.append))
    admin = CapturingAdminClient()
    client.set_admin_client(admin)
    client.process_scada_control_capabilities(cycler_capabilities())
    return client, admin, replies


def send_reboot_picos(client: RelayWatchClient, timeout_seconds: int) -> None:
    client.send_command(H0N.pico_cycler, RebootPicos.RebootPicos, timeout_seconds)


def test_nack_is_paired_with_the_command_it_refuses() -> None:
    client, admin, replies = client_with_replies()
    send_reboot_picos(client, 300)
    dispatch = admin.published[0]
    assert isinstance(dispatch, AdminDispatch)
    trigger_id = dispatch.DispatchTrigger.TriggerId

    nack = DispatchNack(
        FromHandle=f"{H0N.admin}.{H0N.pico_cycler}",
        ToHandle=H0N.admin,
        TriggerId=trigger_id,
        Reason=ScadaCmdRefusalReason.Busy,
        UnixTimeMs=int(time.time() * 1000),
    )
    client.process_mqtt_message(*scada_message(nack))

    assert len(replies) == 1
    reply = replies[0]
    assert not reply.taken
    assert reply.pending is not None
    assert reply.pending.label == RebootPicos.RebootPicos
    assert reply.pending.to_handle == f"{H0N.admin}.{H0N.pico_cycler}"
    assert reply.describe() == f"{reply.reply.FromHandle} refused {RebootPicos.RebootPicos}: Busy"


def test_ack_is_taken_and_a_reply_is_delivered_once() -> None:
    client, admin, replies = client_with_replies()
    send_reboot_picos(client, 300)
    trigger_id = admin.published[0].DispatchTrigger.TriggerId
    ack = DispatchAck(
        FromHandle=f"{H0N.admin}.{H0N.pico_cycler}",
        ToHandle=H0N.admin,
        TriggerId=trigger_id,
        UnixTimeMs=int(time.time() * 1000),
    )
    client.process_mqtt_message(*scada_message(ack))
    client.process_mqtt_message(*scada_message(ack))

    assert [r.taken for r in replies] == [True, True]
    assert replies[0].pending is not None
    assert replies[1].pending is None, "the pending record is consumed by the first reply"


def test_reply_to_a_command_this_panel_did_not_send_is_still_surfaced() -> None:
    client, _, replies = client_with_replies()
    ack = DispatchAck(
        FromHandle=f"{H0N.admin}.{H0N.pico_cycler}",
        ToHandle=H0N.admin,
        TriggerId="1c0d8f5e-3f4a-4b3c-9d2e-7a6b5c4d3e2f",
        UnixTimeMs=int(time.time() * 1000),
    )
    client.process_mqtt_message(*scada_message(ack))
    assert len(replies) == 1 and replies[0].pending is None
    assert replies[0].describe() is None


def test_other_messages_are_not_replies() -> None:
    client, _, replies = client_with_replies()
    reading = SingleReading(ChannelName="hp-odu-pwr", Value=1200, ScadaReadTimeUnixMs=int(time.time() * 1000))
    client.process_mqtt_message(*scada_message(reading))
    assert replies == []
