import logging
from pathlib import Path
from typing import Optional

import dotenv
import rich
import typer
from gwproactor.logging_setup import enable_aiohttp_logging
from trogon import Trogon
from typer.main import get_group

try:
    from tests.atn.atn_config import AtnSettings  # noqa: F401
    from tests.atn.atn_app import AtnApp
except ImportError as e:
    raise ImportError(
        f"ERROR. ({e})\n\n"
        "Running the test atn requires an *extra* entry on the pythonpath, the base directory of the repo.\n"
        "Set this with:\n\n"
        "  export PYTHONPATH=$PYTHONPATH:`pwd`\n"
    )


app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="GridWorks ATN CLI",
)

@app.command()
def config(env_file: str = ".env"):
    """Show AtnSettings."""

    dotenv_file = dotenv.find_dotenv(env_file)
    dotenv_file_exists = Path(dotenv_file).exists() if dotenv_file else False
    rich.print("[cyan bold]+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    rich.print(f"Env file: <{dotenv_file}>  exists:{dotenv_file_exists}")
    # https://github.com/koxudaxi/pydantic-pycharm-plugin/issues/1013
    # noinspection PyArgumentList
    settings = AtnApp.get_settings(env_file=dotenv_file)
    rich.print(settings)
    rich.print("[cyan bold]-----------------------------------------------------------------------------------------------------------\n")

@app.command()
def commands(ctx: typer.Context) -> None:
    """CLI command builder."""
    Trogon(get_group(app), click_context=ctx).run()

@app.command()
def run(
    env_file: str = ".env",
    *,
    dry_run: bool = False,
    verbose: bool = False,
    message_summary: bool = False,
    aiohttp_logging: bool = False,
    paho_logging: bool = False,
    power_meter_logging: bool = False,
    power_meter_logging_verbose: bool = False,
    seconds_per_report: Optional[int] = None,
) -> None:
    """Run the Atn."""
    if aiohttp_logging:
        enable_aiohttp_logging()
    settings = AtnApp.get_settings(
        env_file=env_file,
    )
    if paho_logging:
        settings.paho_logging = True
    if power_meter_logging:
        if settings.power_meter_logging_level > logging.INFO:
            settings.power_meter_logging_level = logging.INFO
    if power_meter_logging_verbose:
        if settings.power_meter_logging_level > logging.DEBUG:
            settings.power_meter_logging_level = logging.DEBUG
    if seconds_per_report is not None:
        settings.seconds_per_report = seconds_per_report
    AtnApp.main(
        app_settings=settings,
        env_file=env_file,
        dry_run=dry_run,
        verbose=verbose,
        message_summary=message_summary,
    )


@app.callback()
def main_app_callback() -> None:
    """Commands for the main atn application"""


# For sphinx:
typer_click_object = typer.main.get_command(app)

if __name__ == "__main__":
    app()
