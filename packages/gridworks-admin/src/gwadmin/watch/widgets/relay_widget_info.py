import logging
import re
from functools import cached_property
from typing import ClassVar
from typing import Optional

from pydantic import BaseModel
from textual.logging import TextualHandler

from gwadmin.watch.clients.relay_client import CommandTransition
from gwadmin.watch.clients.relay_client import RelayConfig
from gwadmin.watch.clients.relay_client import RelayState

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())


class RelayTableName(BaseModel):
    node_name: str = ""
    row_name: str = ""
    relay_number: Optional[int] = None

    relay_table_name_rgx: ClassVar[re.Pattern] = re.compile(
        r"(?P<channel_part>.*)-relay(?P<relay_number>\d+)"
    )

    @classmethod
    def from_node_name(cls, node_name: str) -> "RelayTableName":
        # The suffix parse covers old-convention names (`vdc-relay1`) still in
        # the field; a functional name (`zone1-bedrooms-ops-relay`) has no number.
        relay_match = cls.relay_table_name_rgx.match(node_name)
        if relay_match is None:
            channel_part = node_name.removesuffix("-relay")
            relay_number = None
        else:
            channel_part = relay_match.group("channel_part")
            relay_number = int(relay_match.group("relay_number"))
        return RelayTableName(
            node_name=node_name,
            row_name=" ".join(
                [
                    word.capitalize()
                    for word in channel_part.replace("-", " ").split()
                ]
            ),
            relay_number=relay_number
        )

    @cached_property
    def border_title(self) -> str:
        if self.relay_number is None:
            return self.row_name
        return f"Relay {self.relay_number}: {self.row_name}"


class RelayWidgetConfig(RelayConfig):

    @cached_property
    def table_name(self) -> RelayTableName:
        return RelayTableName.from_node_name(self.about_node_name)

    @classmethod
    def from_config(cls, config: RelayConfig) -> "RelayWidgetConfig":
        return RelayWidgetConfig(**config.model_dump())

    def offered_commands(self, state: Optional[str]) -> list[CommandTransition]:
        """The commands to offer given the observed state, one per
        vocabulary in the order the vocabularies arrive. A two-command
        vocabulary offers the command that leads somewhere else; a
        one-command vocabulary (reboot.picos on five-v-boss) is offered
        when the observed state is its target, since the node only takes
        it at rest. No observed state, or a row with no commands (a relay
        owned by an interior node), offers nothing."""
        if state is None:
            return []
        vocabularies: dict[str, list[CommandTransition]] = {}
        for command in self.commands:
            vocabularies.setdefault(command.event_type, []).append(command)
        offered: list[CommandTransition] = []
        for commands in vocabularies.values():
            if len(commands) == 1:
                if commands[0].to_state == state:
                    offered.append(commands[0])
                continue
            command = next((c for c in commands if c.to_state != state), None)
            if command is not None:
                offered.append(command)
        return offered

    def offered_command(self, state: Optional[str], offer_index: int) -> Optional[CommandTransition]:
        offered = self.offered_commands(state)
        return offered[offer_index] if offer_index < len(offered) else None

    def get_current_state_str(self, state: Optional[str]) -> str:
        return "?" if state is None else state

    def get_action_str(self, state: Optional[str]) -> str:
        return " / ".join(c.event for c in self.offered_commands(state))


class RelayWidgetInfo(BaseModel):
    config: RelayWidgetConfig
    observed: Optional[RelayState] = None

    def get_state(self) -> Optional[str]:
        return None if self.observed is None else self.observed.value
