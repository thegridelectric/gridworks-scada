import logging
import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from typing import Optional

import rich
import typer
from dotenv import dotenv_values
from gwproactor.config.mqtt import TLSInfo
from pydantic import SecretStr

from gwadmin.config import AdminConfig
from gwadmin.config import AdminPaths
from gwadmin.config import CurrentAdminConfig
from gwadmin.config import AdminMQTTClient
from gwadmin.watch.relay_app import RelaysApp, __version__
from gwsproto.data_classes.house_0_names import H0N

CONFIG_ENV_VAR = "GWADMIN_CONFIG_NAME"

DEFAULT_ADMIN_NAME = H0N.admin

ENV_FILE_HELP_TEXT = "Optional path to a .env file used to control configuration name."
CONFIG_NAME_HELP_TEXT = (
         "The subdirectory in $HOME/.config, $HOME/.local/share and "
         "$HOME/.local/state used to store configuration and other Admin "
         "information. The value is read from the first of these sources found, "
         "in order: 1) The --config-name command line option; "
         f"2) The environment variable {CONFIG_ENV_VAR}; "
         f"3) The default value, '{DEFAULT_ADMIN_NAME}'."
)

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help=f"GridWorks Scada Admin Client, version {__version__}",
)

def get_config_name(env_file: str = "", config_name: Optional[str] = None) -> str:
    if config_name is None:
        if CONFIG_ENV_VAR in os.environ and os.environ[CONFIG_ENV_VAR]:
            config_name = os.environ[CONFIG_ENV_VAR]
        elif env_file and Path(env_file).exists():
            config_name = dotenv_values(Path(env_file).resolve()).get(CONFIG_ENV_VAR, DEFAULT_ADMIN_NAME)
        else:
            config_name = DEFAULT_ADMIN_NAME
    return config_name

def available_scadas(admin_config: AdminConfig) -> str:
    available_scadas_str = ""
    for i, existing_scada in enumerate(admin_config.scadas):
        available_scadas_str += f"'{existing_scada}'"
        if i < len(admin_config.scadas) - 1:
            available_scadas_str += ", "
    return available_scadas_str


def get_admin_config(
    *,
    config_name: Optional[str] = None,
    env_file: str = "",
    verbose: int = 0,
    paho_verbose: int = 0,
    show_clock: Optional[bool] = None,
    show_footer: Optional[bool] = None,
    default_scada: Optional[str] = None,
    use_last_scada: Optional[bool] = None,
    default_timeout_seconds: Optional[int] = None,
) -> CurrentAdminConfig:
    paths = AdminPaths(name=get_config_name(env_file=env_file, config_name=config_name))
    if not paths.admin_config_path.exists():
        admin_config = AdminConfig()
    else:
        with paths.admin_config_path.open() as f:
            json_data = f.read()
        admin_config = AdminConfig.model_validate_json(json_data)
    if verbose:
        if verbose == 0:
            verbosity = logging.INFO
        else:
            verbosity = logging.DEBUG
        admin_config.verbosity = verbosity
    if paho_verbose:
        if paho_verbose == 0:
            paho_verbosity = logging.INFO
        else:
            paho_verbosity = logging.DEBUG
        admin_config.paho_verbosity = paho_verbosity
    if show_footer is not None:
        admin_config.show_footer = show_footer
    if show_clock is not None:
        admin_config.show_clock = show_clock
    if default_scada is not None:
        admin_config.default_scada = default_scada
    # if not admin_config.default_scada in admin_config.scadas:
    #     rich.print(
    #         f"[yellow][bold]Default scada '{admin_config.default_scada}' does not exist[/yellow][/bold] "
    #         f"in config. Available scadas: {available_scadas(admin_config)}""."
    #     )
    #     raise typer.Exit(-1)
    #
    if use_last_scada is not None:
        admin_config.use_last_scada = use_last_scada
    if default_timeout_seconds is not None:
        admin_config.default_timeout_seconds = default_timeout_seconds
    return CurrentAdminConfig(
        paths=paths,
        config=admin_config,
    )


class RelayState(StrEnum):
    open = "0"
    closed = "1"

@app.command()
def watch(
    scada: Annotated[
        str,
        typer.Argument(
            help="Short, human-friendly name of the scada configuration to use.",
        ),
    ] = "",
    *,
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose", "-v", count=True, help=(
                "Increase logging verbosity. Maybe specified more than once"
            )
        )
    ] = 0,
    paho_verbose: Annotated[
        int,
        typer.Option(
            "--paho-verbose", count=True,
            help="Enable raw paho.mqtt logging",
        )
    ] = 0,
    show_clock: Annotated[
        Optional[bool],
        typer.Option(
            "--show-clock",
            show_default=False,
            help="Show the clock in the title bar."
        ),
    ] = None,
    show_footer: Annotated[
        Optional[bool],
        typer.Option(
            "--show-footer",
            show_default=False,
            help="Show the footer with shortcut keys."
        ),
    ] = None,
    default_scada: Annotated[
        Optional[str],
        typer.Option(
            "--default-scada",
            show_default=False,
            help="Specify the default scada."
        )
    ] = None,
    use_last_scada: Annotated[
        Optional[bool],
        typer.Option(
            "--use-last-scada",
            show_default=False,
            help="Use the scada last selected when watch was run."
        )
    ] = None,
    default_timeout_seconds: Annotated[
        Optional[int],
        typer.Option(
            "--default-timeout-seconds",
            show_default=False,
        )
    ] = None,
    save: Annotated[
        bool,
        typer.Option(
            "--save",
            help="Save any changes to the configuration produced by command line options."
        )
    ] = False,
    config_name: Annotated[
        Optional[str], typer.Option(help=CONFIG_NAME_HELP_TEXT, show_default=False)
    ] = None,
    env_file: Annotated[str, typer.Option(help=ENV_FILE_HELP_TEXT)] = "",
) -> None:
    """Connect to a GridWorks Scada and watch state information live."""
    current_config = get_admin_config(
        verbose=verbose,
        paho_verbose=paho_verbose,
        show_clock=show_clock,
        show_footer=show_footer,
        default_scada=default_scada,
        use_last_scada=use_last_scada,
        default_timeout_seconds=default_timeout_seconds,
        config_name=config_name,
        env_file=env_file,
    )
    if not scada and current_config.config.use_last_scada:
        scada = current_config.last_scada()
    if not scada:
        scada = current_config.config.default_scada
    if not scada:
        rich.print(
            "[yellow][bold]No scada specified[/yellow][/bold] on command line, "
            "via last-scada-used or in default. "
            "[yellow][bold]Doing nothing.[/yellow][/bold]"
        )
        if not current_config.paths.admin_config_path.exists():
            rich.print(
                f"\nConfig file {current_config.paths.admin_config_path} "
                "does not exist. To create a default configuration run:"
            )
            rich.print("\n  [green][bold]gwa mkconfig[/green]")
            rich.print("\nThen, to add configuration for your scada, run:")
            rich.print("\n  [green][bold]gwa add-scada[/green]\n")
        raise typer.Exit(2)
    if not scada in current_config.config.scadas:
        rich.print(
            f"[yellow][bold]Specified scada '{scada}' does not exist[/yellow][/bold] "
            f"in config. Available scadas: {available_scadas(current_config.config)}""."
        )
        raise typer.Exit(3)
    current_config.curr_scada = scada
    rich.print(f"Using scada '{scada}'.")
    if current_config.config.use_last_scada:
        current_config.save_curr_scada(scada)
    if save:
        rich.print(f"Saving configuration in {current_config.paths.admin_config_path}")
        current_config.save_config()
    watch_app = RelaysApp(settings=current_config)
    watch_app.run()

@app.command()
def config_file(
    config_name: Annotated[
        Optional[str], typer.Option(help=CONFIG_NAME_HELP_TEXT, show_default=False)
    ] = None,
    env_file: Annotated[str, typer.Option(help=ENV_FILE_HELP_TEXT)] = "",
) -> None:
    """Show path to admin config file."""
    paths = AdminPaths(name=get_config_name(env_file=env_file, config_name=config_name))
    rich.print(paths.admin_config_path)



@app.command()
def config(
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True)] = 0,
    paho_verbose: Annotated[int, typer.Option("--paho-verbose", count=True)] = 0,
    show_clock: Annotated[
        Optional[bool],
        typer.Option(
            "--show-clock",
            show_default=False,
            help="Show the clock in the title bar."
        ),
    ] = None,
    show_footer: Annotated[
        Optional[bool],
        typer.Option(
            "--show-footer",
            show_default=False,
            help="Show the footer with shortcut keys."
        ),
    ] = None,
    default_scada: Annotated[
        Optional[str],
        typer.Option(
            "--default-scada",
            show_default=False,
            help="Specify the default scada."
        )
    ] = None,
    use_last_scada: Annotated[
        Optional[bool],
        typer.Option(
            "--use-last-scada",
            show_default=False,
            help="Use the scada last selected when watch was run."
        )
    ] = None,
    default_timeout_seconds: Annotated[
        Optional[int],
        typer.Option(
            "--default-timeout-seconds",
            show_default=False,
        )
    ] = None,
    save: Annotated[
        bool,
        typer.Option(
            "--save",
            help="Save any changes to the configuration produced by command line options."
        )
    ] = False,
    config_name: Annotated[
        Optional[str], typer.Option(help=CONFIG_NAME_HELP_TEXT, show_default=False)
    ] = None,
    env_file: Annotated[str, typer.Option(help=ENV_FILE_HELP_TEXT)] = "",
) -> None:
    """Show and, optionally, change the admin configuration."""
    current_config = get_admin_config(
        verbose=verbose,
        paho_verbose=paho_verbose,
        show_clock=show_clock,
        show_footer=show_footer,
        default_scada=default_scada,
        use_last_scada=use_last_scada,
        default_timeout_seconds=default_timeout_seconds,
        config_name=config_name,
        env_file=env_file,
    )
    rich.print(current_config.config)
    if save:
        rich.print(f"Saving configuration in {current_config.paths.admin_config_path}")
        current_config.save_config()


@app.command()
def mkconfig(
    *,
    config_name: Annotated[
        Optional[str], typer.Option(help=CONFIG_NAME_HELP_TEXT, show_default=False)
    ] = None,
    env_file: Annotated[str, typer.Option(help=ENV_FILE_HELP_TEXT)] = "",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="""Overwrites existing configuration file.
            [yellow][bold]WARNING: [/yellow][/bold]--force will [red][bold]PERMANENTLY DELETE[/red][/bold]
            this Admin configuration.""",
        ),
    ] = False,
) -> None:
    """Create a default configuration file."""
    paths = AdminPaths(name=get_config_name(env_file=env_file, config_name=config_name))
    if paths.admin_config_path.exists():
        if not force:
            rich.print(
                f"Configuartion file {paths.admin_config_path} [yellow][bold]already exists. Doing nothing.[/yellow][/bold]"
            )
            rich.print(f"Use --force to overwrite existing configuration.")
            return
        else:
            rich.print(
                f"[yellow][bold]DELETING existing configuration[/yellow][/bold]."
            )
            paths.admin_config_path.unlink()
    rich.print(f"Creating {paths.admin_config_path}")
    paths.mkdirs(parents=True, exist_ok=True)
    with paths.admin_config_path.open(mode="w") as file:
        file.write(AdminConfig().model_dump_json(indent=2))


@app.command()
def add_scada(
    name: Annotated[
        str, typer.Argument(
            help=(
                "The short, human-friendly name of the scada to add."
            )
        )
    ],
    *,
    long_name: str = "",
    host = "localhost",
    port = 1883,
    username: Optional[str] = None,
    password: Optional[str] = None,
    use_tls: bool = False,
    default: Annotated[
        bool, typer.Option(
            help=(
                "Whether to set this scada as the default scada."
            )
        )
    ] = False,
    config_name: Annotated[
        Optional[str], typer.Option(help=CONFIG_NAME_HELP_TEXT, show_default=False)
    ] = None,
    env_file: Annotated[str, typer.Option(help=ENV_FILE_HELP_TEXT)] = "",
) -> None:
    """Add configuration to connect to a particular Scada."""
    current_config = get_admin_config(config_name=config_name, env_file=env_file)
    if current_config.add_scada(
            name,
            long_name=long_name,
            mqtt_client_config=AdminMQTTClient(
                host=host,
                port=port,
                username=username,
                password=SecretStr(password),
                tls=TLSInfo(use_tls=use_tls),
            )
    ):
        rich.print(f"Adding default configuration for scada '{name}'")
        if len(current_config.config.scadas) == 1 or default:
            current_config.config.default_scada = name
        rich.print(f"Updating config file {current_config.paths.admin_config_path}")
        with current_config.paths.admin_config_path.open(mode="w") as f:
            f.write(current_config.config.model_dump_json(indent=2))
    else:
        rich.print(
            f"Scada with name {name} [yellow][bold]already exists. Doing nothing.[/yellow][/bold]"
        )
        rich.print(
            "Use --force to overwrite existing configuration[/yellow][/bold] or modify config file."
        )
        return


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
