import typer

from gwadmin.tdemo.actions import ActionsApp
from gwadmin.tdemo.stopwatch import StopwatchApp
from gwadmin.tdemo.switch import SwitchApp

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="Textual demo apps",
)


@app.command()
def stopwatch():
    """Run textual stopwatch demo"""
    stopwatch_app = StopwatchApp()
    stopwatch_app.run()

@app.command()
def switch():
    """Run textual switch demo"""
    switch_app = SwitchApp()
    switch_app.run()

@app.command()
def actions():
    """Run textual actions demo"""
    actions_app = ActionsApp()
    actions_app.run()


@app.callback()
def _main() -> None: ...


if __name__ == "__main__":
    app()
