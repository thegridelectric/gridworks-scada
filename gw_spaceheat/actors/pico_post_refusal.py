"""A pico post an actor refuses is a field condition: a Warning glitch, at
most one per pico and condition per REFUSED_POST_REPORT_S."""
import json
import time
from typing import NamedTuple

from gwproto import Message
from pydantic import BaseModel

from actors.sh_node_actor import ShNodeActor
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch

REFUSED_POST_REPORT_S = 24 * 3600  # a refused post is reported once a day per pico and condition


class Refusal(NamedTuple):
    """One refused post. `pico` is the HwUid the post names, or the actor's
    node name when the post names none; `condition` is the glitch Summary
    and, with `pico`, the key of the daily limit; `details` is the Details."""

    pico: str
    condition: str
    details: str


def first_line(exception: BaseException) -> str:
    lines = str(exception).splitlines()
    return f"{type(exception).__name__}: {lines[0] if lines else ''}"


def refused_post(
    node_name: str, text: str, exception: BaseException, expected: type[BaseModel]
) -> Refusal:
    """Classify a post that did not decode as `expected`: a version the
    scada does not take (when `expected` declares one), or any other
    refusal."""
    try:
        posted = json.loads(text)
    except ValueError:
        posted = None
    if not isinstance(posted, dict):
        return Refusal(
            node_name, "refused-post", f"{node_name} cannot decode a post: {first_line(exception)}"
        )
    pico = str(posted.get("HwUid") or node_name)
    fields = expected.model_fields
    type_name = fields["TypeName"].default
    version = fields["Version"].default if "Version" in fields else None
    if version is not None and posted.get("TypeName") == type_name and posted.get("Version") != version:
        return Refusal(
            pico,
            "params-version",
            f"{node_name} {pico} posts {type_name} {posted.get('Version')}; the scada takes {version}",
        )
    return Refusal(pico, "refused-post", f"{node_name} {pico} post refused: {first_line(exception)}")


def unreadable_post(node_name: str, exception: BaseException) -> Refusal:
    return Refusal(
        node_name, "unreadable-post", f"{node_name} cannot read a post body: {first_line(exception)}"
    )


def unknown_pico(node_name: str, posted_hw_uid: str, layout_hw_uid: str | None) -> Refusal:
    return Refusal(
        posted_hw_uid,
        "unknown-pico",
        f"{posted_hw_uid} posts as {node_name}; the layout names {layout_hw_uid}",
    )


class RefusedPosts:
    """The refusals one actor has reported and when. The web handlers call
    it on the IO loop, so the glitch goes to the actor through
    send_threadsafe and the actor sends it on."""

    def __init__(self, actor: ShNodeActor) -> None:
        self.actor = actor
        self.reported_s: dict[tuple[str, str], float] = {}

    def report(self, refusal: Refusal) -> None:
        key = (refusal.pico, refusal.condition)
        now = time.time()
        last = self.reported_s.get(key)
        if last is not None and now - last < REFUSED_POST_REPORT_S:
            return
        self.reported_s[key] = now
        self.actor.services.send_threadsafe(
            Message(
                Src=self.actor.name,
                Dst=self.actor.name,
                Payload=Glitch(
                    FromGNodeAlias=self.actor.layout.scada_g_node_alias,
                    Node=self.actor.name,
                    Type=LogLevel.Warning,
                    Summary=refusal.condition,
                    Details=refusal.details,
                ),
            )
        )
