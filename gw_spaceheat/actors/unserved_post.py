"""A POST the scada's web server answers but no actor serves. The box can
only learn of it once the sender posts, so it is a Warning glitch: once per
path per day, with the posted identity, and a log line on every post."""
import json
import logging

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gwproto import Message

from actors.glitch_limit import REPEAT_GLITCH_S, GlitchLimit
from gwproactor import Proactor
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch

UNSERVED_POST_PATH = "/{tail:.*}"  # registered last, after every actor's routes


def posted_identity(text: str | None) -> str:
    """What the post says it is: its HwUid and TypeName when the body is a
    JSON object that names them, or nothing."""
    try:
        posted = json.loads(text) if text is not None else None
    except ValueError:
        return ""
    if not isinstance(posted, dict):
        return ""
    parts = [str(posted[k]) for k in ("HwUid", "TypeName", "Version") if posted.get(k)]
    return " ".join(parts)


class UnservedPosts:
    """The catch-all handler for the scada's web server."""

    def __init__(
        self, proactor: Proactor, node_name: str, scada_g_node_alias: str, logger: logging.Logger
    ) -> None:
        self.proactor = proactor
        self.node_name = node_name
        self.scada_g_node_alias = scada_g_node_alias
        self.logger = logger
        self.limit = GlitchLimit(REPEAT_GLITCH_S)

    async def handle(self, request: Request) -> Response:
        try:
            text: str | None = await request.text()
        except Exception:  # noqa: BLE001
            text = None
        identity = posted_identity(text)
        details = f"POST {request.path} is served by no actor" + (
            f"; the post says {identity}" if identity else ""
        )
        self.logger.warning(details)
        if self.limit.due(request.path):
            self.proactor.send_threadsafe(
                Message(
                    Src=self.node_name,
                    Dst=self.node_name,
                    Payload=Glitch(
                        FromGNodeAlias=self.scada_g_node_alias,
                        Node=self.node_name,
                        Type=LogLevel.Warning,
                        Summary="unserved-post",
                        Details=details,
                    ),
                )
            )
        return Response(status=404)
