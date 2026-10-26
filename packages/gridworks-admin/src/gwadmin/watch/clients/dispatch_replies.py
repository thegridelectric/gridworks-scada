"""Matches the scada's dispatch ack / nack replies to the commands the panel
sent. Each client remembers what it published by TriggerId; a reply that
comes back over the admin link is paired with that record so the panel can
say which command was taken or refused, and why."""

import threading
import time
from typing import NamedTuple, Optional

from gwproto import Message as GWMessage
from gwproto import MQTTTopic
from gwsproto.named_types import DispatchAck, DispatchNack
from gwsproto.property_format import HandleName, UUID4Str

from gwadmin.watch.clients.admin_client import type_name

PENDING_MAX_AGE_S = 600
"""A command with no reply after this long is forgotten; a reply to it is
still surfaced, unpaired."""


class PendingDispatch(NamedTuple):
    """A command the panel published and has not yet heard back on."""

    to_handle: HandleName
    """The command's ToHandle: the node asked."""
    label: str
    """What the operator asked for, in the panel's words (e.g. "Reboot picos",
    "primary-010v -> 65")."""
    sent_s: float
    """Wall-clock seconds when the command was published."""


class DispatchReply(NamedTuple):
    """One ack or nack off the admin link, paired with the command it answers
    when that command was sent from this panel."""

    reply: DispatchAck | DispatchNack
    pending: Optional[PendingDispatch]

    @property
    def taken(self) -> bool:
        return isinstance(self.reply, DispatchAck)

    def describe(self) -> Optional[str]:
        """The one line the panel shows, e.g. "admin.buffer-bottom-elt-relay
        took OpenRelay"; None for a reply to a command this panel did not
        send, which the panel keeps silent."""
        if self.pending is None:
            return None
        if isinstance(self.reply, DispatchNack):
            return f"{self.reply.FromHandle} refused {self.pending.label}: {self.reply.Reason.value}"
        return f"{self.reply.FromHandle} took {self.pending.label}"


class DispatchReplyTracker:
    """Thread-safe: note() runs on the caller's thread, match() on Paho's."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[UUID4Str, PendingDispatch] = {}

    def note(self, trigger_id: UUID4Str, to_handle: HandleName, label: str) -> None:
        now = time.time()
        with self._lock:
            self._pending = {
                k: v for k, v in self._pending.items() if now - v.sent_s < PENDING_MAX_AGE_S
            }
            self._pending[trigger_id] = PendingDispatch(to_handle, label, now)

    def match(self, topic: str, payload: bytes) -> Optional[DispatchReply]:
        """The reply carried by this message, or None when it is not one."""
        message_type = MQTTTopic.decode(topic).message_type
        if message_type == type_name(DispatchAck):
            reply: DispatchAck | DispatchNack = GWMessage[DispatchAck].model_validate_json(payload).Payload
        elif message_type == type_name(DispatchNack):
            reply = GWMessage[DispatchNack].model_validate_json(payload).Payload
        else:
            return None
        with self._lock:
            pending = self._pending.pop(reply.TriggerId, None)
        return DispatchReply(reply, pending)
