import logging
from typing import Optional

from textual.app import RenderResult
from textual.logging import TextualHandler
from textual.reactive import Reactive
from textual.reactive import reactive
from textual.widgets import Static

from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())

class RelayStateText(Static):
    energized: Reactive[Optional[bool]] = reactive(None)
    config: Reactive[RelayWidgetConfig] = reactive(RelayWidgetConfig)

    def __init__(
        self,
        energized: Optional[bool] = None,
        config: Optional[RelayWidgetConfig] = None,
        *args,
        logger: logging.Logger = module_logger,
        **kwargs
    ):
        self.logger = logger
        super().__init__(*args, **kwargs)
        self.energized = energized
        self.config = config or RelayWidgetConfig()

    def render(self) -> RenderResult:
        return self.config.get_state_str(self.energized)
