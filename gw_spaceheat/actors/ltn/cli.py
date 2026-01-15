from pathlib import Path

import dotenv
import rich
import typer
from gwproactor.logging_setup import enable_aiohttp_logging
from trogon import Trogon
from typer.main import get_group
from ltn_app import LtnApp


app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="GridWorks LTN CLI",
)

@app.command()
def config(env_file: str = ".env"):
    """Show LtnSettings."""

    dotenv_file = dotenv.find_dotenv(env_file)
    dotenv_file_exists = Path(dotenv_file).exists() if dotenv_file else False
    rich.print("[cyan bold]+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    rich.print(f"Env file: <{dotenv_file}>  exists:{dotenv_file_exists}")
    # https://github.com/koxudaxi/pydantic-pycharm-plugin/issues/1013
    # noinspection PyArgumentList
    settings = LtnApp.get_settings(env_file=dotenv_file)
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
) -> None:
    """Run the Ltn."""
    if aiohttp_logging:
        enable_aiohttp_logging()
    settings = LtnApp.get_settings(
        env_file=env_file,
    )

    LtnApp.main(
        app_settings=settings,
        env_file=env_file,
        dry_run=dry_run,
        verbose=verbose,
        message_summary=message_summary,
    )


@app.callback()
def main_app_callback() -> None:
    """Commands for the main ltn application"""


# For sphinx:
typer_click_object = typer.main.get_command(app)

if __name__ == "__main__":
    app()
