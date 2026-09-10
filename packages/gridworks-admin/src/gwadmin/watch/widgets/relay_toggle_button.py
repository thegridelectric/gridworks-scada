import logging
from typing import Literal
from typing import Optional

from textual.logging import TextualHandler
from textual.message import Message
from textual.reactive import Reactive
from textual.reactive import reactive
from textual.widgets import Button

from gwadmin.config import DEFAULT_ADMIN_TIMEOUT
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwadmin.watch.widgets.timer import TimerDigits
from gwadmin.watch.widgets.time_input import TimeInput
from gwadmin.watch.widgets.keepalive import KeepAliveButton

module_logger = logging.getLogger(__name__)
module_logger.addHandler(TextualHandler())


class RelayToggleButton(Button, can_focus=True):
    """Sends one of the selected row's offered commands: the relay event,
    TurnHpOnOff to hp-boss, TurnOff or RebootPicos to five-v-boss,
    whichever the row's vocabularies offer from its observed state. The
    panel has one button per offer slot (`offer_index`): the first offer
    on `n`, the second on `p`; the keys bind on the Relays widget."""

    state: Reactive[Optional[str]] = reactive(None)
    config: Reactive[Optional[RelayWidgetConfig]] = reactive(None)
    timeout_seconds: int

    def __init__(
        self,
        offer_index: int,
        state: Optional[str] = None,
        config: Optional[RelayWidgetConfig] = None,
        default_timeout_seconds: int = DEFAULT_ADMIN_TIMEOUT,
        logger: logging.Logger = module_logger,
        **kwargs
    ) -> None:
        self.logger = logger
        self.offer_index = offer_index
        super().__init__(variant=self.variant_from_state(state), **kwargs)
        self.default_timeout_seconds = default_timeout_seconds
        self.set_reactive(RelayToggleButton.state, state)
        self.set_reactive(RelayToggleButton.config, config or None)
        self.update_label()

    @classmethod
    def variant_from_state(cls, state: Optional[str]) -> Literal["default", "warning"]:
        return "default" if state is None else "warning"

    def next_event(self) -> Optional[str]:
        if self.config is None:
            return None
        command = self.config.offered_command(self.state, self.offer_index)
        return None if command is None else command.event

    def update_label(self) -> None:
        """The first slot's button is always shown, empty and disabled when
        the row offers nothing; a later slot's button is hidden when it has
        no offer, so a one-offer row keeps a single full-width button."""
        event = self.next_event()
        self.display = self.offer_index == 0 or event is not None
        if event is None:
            self.disabled = True
            self.label = ""
            return
        self.disabled = False
        self.label = event

    def watch_state(self) -> None:
        self.variant = self.variant_from_state(self.state)
        self.update_label()

    def watch_config(self) -> None:
        if self.config is None:
            self.border_title = ""
        self.update_label()

    class Pressed(Message):
        def __init__(self, about_node_name: str, event: str, timeout_seconds: int) -> None:
            super().__init__()
            self.about_node_name = about_node_name
            self.event = event
            self.timeout_seconds = timeout_seconds

    def read_timeout(self) -> int:
        input_value = self.app.query_one(TimeInput).value
        try:
            time_in_minutes = float(input_value) if input_value else int(self.default_timeout_seconds/60)
            return int(time_in_minutes * 60)
        except ValueError:
            return self.default_timeout_seconds

    def action_toggle_relay(self) -> None:
        self.on_button_pressed()

    def on_button_pressed(self) -> None:
        event = self.next_event()
        if self.config is None or event is None:
            return
        self.timeout_seconds = self.read_timeout()
        self.post_message(
            RelayToggleButton.Pressed(
                self.config.about_node_name,
                event,
                self.timeout_seconds
            )
        )
        self.post_message(KeepAliveButton.Pressed(self.timeout_seconds))
        timer_display = self.app.query_one(TimerDigits)
        timer_display.restart(self.timeout_seconds)
