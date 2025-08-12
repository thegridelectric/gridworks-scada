import logging
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from typing import Optional

import dotenv
import rich
import typer

from admin.tdemo.cli import app as tdemo_cli
from admin.settings import AdminClientSettings
from admin.watch.relay_app import RelaysApp, __version__
from admin.watch.watchex.watchex_app import WatchExApp

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="GridWorks Scada Admin Client, version {__version__}",
)

app.add_typer(tdemo_cli, name="demo", help="Textual demo commands.")

DEFAULT_TARGET: str = "d1.isone.me.versant.keene.orange.scada"

class RelayState(StrEnum):
    open = "0"
    closed = "1"

def watch_settings(
    target: str = "",
    env_file: str = ".env",
    verbose: int = 0,
    paho_verbose: int = 0,
    show_clock: bool = False,
) -> AdminClientSettings:
    # https://github.com/koxudaxi/pydantic-pycharm-plugin/issues/1013
    # noinspection PyArgumentList
    settings = AdminClientSettings(
        _env_file=dotenv.find_dotenv(env_file),
        show_clock=show_clock,
    ).update_paths_name("admin")
    if target:
        settings.target_gnode = target
    elif not settings.target_gnode:
        settings.target_gnode = DEFAULT_TARGET
    if verbose:
        if verbose == 1:
            verbosity = logging.INFO
        else:
            verbosity = logging.DEBUG
        settings.verbosity = verbosity
    if paho_verbose:
        if paho_verbose == 1:
            paho_verbosity = logging.INFO
        else:
            paho_verbosity = logging.DEBUG
        settings.paho_verbosity = paho_verbosity
    return settings

@app.command()
def watch(
    target: str = "",
    env_file: str = ".env",
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose", "-v", count=True
        )
    ] = 0,
    paho_verbose: Annotated[
        int,
        typer.Option(
            "--paho-verbose", count=True
        )
    ] = 0,
    show_clock: Annotated[
        bool,
        typer.Option(
            "--show-clock",
        )
    ] = False,

) -> None:
    """Watch and set relays."""
    settings = watch_settings(
        target,
        env_file,
        verbose,
        paho_verbose,
        show_clock=show_clock,
    )
    rich.print(settings)
    watch_app = RelaysApp(settings=settings)
    watch_app.run()

@app.command()
def watchex(
    target: str = "",
    env_file: str = ".env",
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose", "-v", count=True
        )
    ] = 0,
    paho_verbose: Annotated[
        int,
        typer.Option(
            "--paho-verbose", count=True
        )
    ] = 0
) -> None:
    """Watch and set relays with experimental features"""
    settings = watch_settings(target, env_file, verbose, paho_verbose)
    rich.print(settings)
    watch_app = WatchExApp(settings=settings)
    watch_app.run()

@app.command()
def config(
    target: str = "",
    env_file: str = ".env",
        verbose: Annotated[
            int,
            typer.Option(
                "--verbose", "-v", count=True
            )
        ] = 0,
        paho_verbose: Annotated[
            int,
            typer.Option(
                "--paho-verbose", count=True
            )
        ] = 0
) -> None:
    """Show admin settings."""
    settings = watch_settings(target, env_file, verbose, paho_verbose)
    rich.print(
        f"Env file: <{env_file}>  exists: {bool(env_file and Path(env_file).exists())}"
    )
    rich.print(settings)
    missing_tls_paths_ = settings.check_tls_paths_present(raise_error=False)
    if missing_tls_paths_:
        rich.print(missing_tls_paths_)


def version_callback(value: bool):
    if value:
        print(f"gws admin {__version__}")
        raise typer.Exit()

@app.callback()
def _main(
    _version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit."
        ),
    ] = None,
) -> None: ...


if __name__ == "__main__":
    app()
