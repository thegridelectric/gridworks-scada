import logging
import re
from functools import cached_property
from typing import ClassVar
from typing import Optional

from pydantic import BaseModel
from textual.logging import TextualHandler

from gwadmin.watch.clients.dac_client import DACConfig
from gwadmin.watch.clients.dac_client import DACState

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())


class DACTableName(BaseModel):
    channel_name: str = ""
    row_name: str = ""

    dac_table_name_rgx: ClassVar[re.Pattern] = re.compile(
        r"(?P<channel_part>.*)-010v"
    )

    @classmethod
    def from_channel_name(cls, channel_name: str) -> "DACTableName":
        dac_match = cls.dac_table_name_rgx.match(channel_name)
        if dac_match is None:
            channel_part = channel_name
        else:
            channel_part = dac_match.group("channel_part")
        return DACTableName(
            channel_name=channel_name,
            row_name=" ".join(
                [
                    word.capitalize()
                    for word in channel_part.replace("-", " ").split()
                ]
            ),
        )

    @cached_property
    def border_title(self) -> str:
        return self.row_name

class DACWidgetConfig(DACConfig):

    @cached_property
    def table_name(self) -> DACTableName:
        return DACTableName.from_channel_name(self.channel_name)

    @classmethod
    def from_config(
            cls,
            config: DACConfig,
    ) -> "DACWidgetConfig":
        return DACWidgetConfig(
            **config.model_dump()
        )

    @classmethod
    def get_state_str(cls, value: Optional[int]) -> str:
        if value is None:
            return "?"
        return f"{value:3d}"

    def get_current_state_str(self, value: Optional[int]) -> str:
        return self.get_state_str(value)


class DACWidgetInfo(BaseModel):
    config: DACWidgetConfig = DACWidgetConfig()
    observed: Optional[DACState] = None

    @classmethod
    def get_observed_state(cls, observed) -> Optional[int]:
        if observed is not None:
            return observed.value
        return None

    def get_state(self) -> Optional[int]:
        return self.get_observed_state(self.observed)

    def get_state_str(self) -> str:
        return self.config.get_state_str(self.get_state())

