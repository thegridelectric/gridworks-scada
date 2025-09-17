import logging
import re
from functools import cached_property
from typing import ClassVar
from typing import Optional

from pydantic import BaseModel
from textual.logging import TextualHandler

from gwadmin.watch.clients.relay_client import RelayConfig
from gwadmin.watch.clients.relay_client import RelayEnergized
from gwadmin.watch.clients.relay_client import RelayState

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())


class RelayTableName(BaseModel):
    channel_name: str = ""
    row_name: str = ""
    relay_number: Optional[int] = None

    relay_table_name_rgx: ClassVar[re.Pattern] = re.compile(
        r"(?P<channel_part>.*)-relay(?P<relay_number>\d+)"
    )

    @classmethod
    def from_channel_name(cls, channel_name: str) -> "RelayTableName":
        relay_match = cls.relay_table_name_rgx.match(channel_name)
        if relay_match is None:
            channel_part = channel_name
            relay_number = None
        else:
            channel_part = relay_match.group("channel_part")
            relay_number = int(relay_match.group("relay_number"))
        return RelayTableName(
            channel_name=channel_name,
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
    energized_icon: str = "⚡"
    deenergized_icon: str = "-"
    show_icon: bool = True

    @cached_property
    def table_name(self) -> RelayTableName:
        return RelayTableName.from_channel_name(self.channel_name)

    @classmethod
    def from_config(
            cls,
            config: RelayConfig,
            energized_icon: str = "🔴",
            deenergized_icon: str = "⚫️",
            show_icon: bool = True,
    ) -> "RelayWidgetConfig":
        return RelayWidgetConfig(
            energized_icon=energized_icon,
            deenergized_icon=deenergized_icon,
            show_icon=show_icon,
            **config.model_dump()
        )

    def get_state_str(self, energized: Optional[bool], *, show_icon: Optional[bool] = None) -> str:
        if energized is None:
            icon = "?"
            description = "?"
        elif energized:
            icon = self.energized_icon
            description = self.energizing_event
        else:
            icon = self.deenergized_icon
            description = self.de_energizing_event
        if (show_icon is None and self.show_icon) or show_icon is True:
            return f"{icon} {description}"
        return description

    def get_current_state_str(self, energized: Optional[bool], icon: Optional[bool] = False) -> str:
        if energized is None:
            return "?"
        if energized:
            if icon:
                return self.energized_icon
            return self.energized_state
        else:
            if icon:
                return self.deenergized_icon
            return self.deenergized_state
    

class RelayWidgetInfo(BaseModel):
    config: RelayWidgetConfig = RelayWidgetConfig()
    observed: Optional[RelayState] = None

    @classmethod
    def get_observed_state(cls, observed) -> Optional[bool]:
        if observed is not None:
            return observed.value == RelayEnergized.energized
        return None

    def get_state(self) -> Optional[bool]:
        return self.get_observed_state(self.observed)

    def get_state_str(self) -> str:
        return self.config.get_state_str(self.get_state())

    def get_energize_str(self) -> str:
        return self.config.get_energize_str(True)

    def get_deenergize_str(self) -> str:
        return self.config.get_energize_str(False)
