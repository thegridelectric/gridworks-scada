from textual.app import App, ComposeResult
from textual.widgets import Button
from textual.widgets import Footer
from textual.widgets import Static

TEXT = """
[b]Set your background[/b]
[@click=set_background('cyan')]Cyan[/]
[@click=set_background('magenta')]Magenta[/]
[@click=set_background('yellow')]Yellow[/]
"""


class ColorSwitcher(Static, can_focus=True):
    BINDINGS = [
        ("o", "set_background('olive')", "olive"),
        ("w", "set_background('ansi_white')", "ansi_white"),
        ("s", "set_background('silver')", "silver"),
    ]
    def action_set_background(self, color: str) -> None:
        self.styles.background = color


class ActionsApp(App):
    CSS_PATH = "actions05.tcss"
    BINDINGS = [
        ("q", "quit"),
        ("ctrl+c", "quit"),
        ("r", "set_background('red')", "Red"),
        ("g", "set_background('green')", "Green"),
        ("b", "set_background('blue')", "Blue"),
    ]

    def compose(self) -> ComposeResult:
        yield ColorSwitcher(TEXT)
        yield ColorSwitcher(TEXT)
        yield Button("foo")
        yield Footer()

    def action_set_background(self, color: str) -> None:
        self.screen.styles.background = color


if __name__ == "__main__":
    app = ActionsApp()
    app.run()