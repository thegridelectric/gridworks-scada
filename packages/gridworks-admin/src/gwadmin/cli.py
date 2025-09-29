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
from gwadmin.config import ScadaConfig
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
    show_selected_scada_block: Optional[bool] = None,
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
        if verbose == 1:
            verbosity = logging.INFO
        else:
            verbosity = logging.DEBUG
        admin_config.verbosity = verbosity
    if paho_verbose:
        if paho_verbose == 1:
            paho_verbosity = logging.INFO
        else:
            paho_verbosity = logging.DEBUG
        admin_config.paho_verbosity = paho_verbosity
    if show_footer is not None:
        admin_config.show_footer = show_footer
    if show_clock is not None:
        admin_config.show_clock = show_clock
    if show_selected_scada_block is not None:
        admin_config.show_selected_scada_block = show_selected_scada_block
    if default_scada is not None:
        admin_config.default_scada = default_scada
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
            show_default=False,
            help="Show the clock in the title bar."
        ),
    ] = None,
    show_footer: Annotated[
        Optional[bool],
        typer.Option(
            show_default=False,
            help="Show the footer with shortcut keys."
        ),
    ] = None,
    show_scada_block: Annotated[
        Optional[bool],
        typer.Option(
            show_default=False,
            help="Show a colored block for the selected scada in the select section."
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
        show_selected_scada_block=show_scada_block,
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
            "[red][bold]No scada specified[/red][/bold] on command line, "
            "via last-scada-used or in default. "
            "[red][bold]Doing nothing.[/red][/bold]"
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
            f"[red][bold]Specified scada '{scada}' does not exist[/red][/bold] "
            f"in config. Available scadas: {available_scadas(current_config.config)}""."
        )
        raise typer.Exit(3)
    current_config.curr_scada = scada
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
            show_default=False,
            help="Show the clock in the title bar."
        ),
    ] = None,
    show_footer: Annotated[
        Optional[bool],
        typer.Option(
            show_default=False,
            help="Show the footer with shortcut keys."
        ),
    ] = None,
    show_scada_block: Annotated[
        Optional[bool],
        typer.Option(
            show_default=False,
            help="Show a colored block for the selected scada in the select section."
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
    json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Generate output in json format."
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
        show_selected_scada_block=show_scada_block,
        default_scada=default_scada,
        use_last_scada=use_last_scada,
        default_timeout_seconds=default_timeout_seconds,
        config_name=config_name,
        env_file=env_file,
    )
    if json:
        print(current_config.model_dump_json(indent=2))
    else:
        rich.print(current_config.config)
    if save:
        if not json:
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
            [red][bold]WARNING: [/red][/bold]--force will [red][bold]PERMANENTLY DELETE[/red][/bold]
            this Admin configuration.""",
        ),
    ] = False,
) -> None:
    """Create a default configuration file."""
    paths = AdminPaths(name=get_config_name(env_file=env_file, config_name=config_name))
    if paths.admin_config_path.exists():
        if not force:
            rich.print(
                f"Configuartion file {paths.admin_config_path} [red][bold]already exists. Doing nothing.[/red][/bold]"
            )
            rich.print(f"Use --force to overwrite existing configuration.")
            raise typer.Exit(4)
        else:
            rich.print(
                f"[red][bold]DELETING existing configuration[/red][/bold]."
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
    long_name: Annotated[
        Optional[str], typer.Option(
            show_default=False,
            help=(
                "The long name or 'gnode alias' of the scada. This name is used"
                " to construct the MQTT topic for connecting to the scada."
            )
        )
    ] = None,
    host: Annotated[
        Optional[str],
        typer.Option(
            show_default=False,
            help=(
                "The IP address or domain name of the scada. "
                "Default is 'localhost'."
            )
        )
    ] = None,
    port: Annotated[
        Optional[int],
        typer.Option(
            show_default=False,
            help=(
                "The TCP/IP port in use for MQTT on the scada. Default is 1883."
            )
        )
    ] = None,
    username:  Annotated[
        Optional[str],
        typer.Option(
            show_default=False,
            help="The MQTT username, if any.",
        )
    ] = None,
    password:  Annotated[
        Optional[str],
        typer.Option(
            show_default=False,
            help="The MQTT password, if any.",
        )
    ] = None,
    use_tls:  Annotated[
        Optional[bool],
        typer.Option(help="Whether to use TLS for this scada.")
    ] = None,
    default: Annotated[
        bool,
        typer.Option(help="Whether to set this scada as the default scada.")
    ] = None,
    enabled: Annotated[
        bool, typer.Option(help="Whether current configuration is enabled.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite any existing scada configuration.")
    ] = False,
    update: Annotated[
        bool, typer.Option("--update", help="Update the selected scada.")
    ] = False,
    config_name: Annotated[
        Optional[str], typer.Option(help=CONFIG_NAME_HELP_TEXT, show_default=False)
    ] = None,
    env_file: Annotated[str, typer.Option(help=ENV_FILE_HELP_TEXT)] = "",
) -> None:
    """Add configuration to connect to a particular Scada."""
    current_config = get_admin_config(config_name=config_name, env_file=env_file)
    if name not in current_config.config.scadas or force:
        if name not in current_config.config.scadas:
            rich.print(f"Adding configuration for scada '{name}'")
        else:
            rich.print("Overwriting configuration for scada '{name}'")
        current_config.config.scadas[name] = ScadaConfig(
            enabled=True if enabled is None else enabled,
            long_name=long_name if long_name is not None else "",
            mqtt=AdminMQTTClient(
                host=host if host is not None else "localhost",
                port=port if port is not None else 1883,
                username=username if username is not None else "",
                password=SecretStr(password if password is not None else ""),
                tls=TLSInfo(use_tls=use_tls if use_tls is not None else False),
            )
        )
    elif update:
        rich.print(f"Updating configuration for scada '{name}'")
        scada_config = current_config.config.scadas[name]
        if enabled is not None:
            scada_config.enabled = enabled
        if long_name is not None:
            scada_config.long_name = long_name
        if host is not None:
            scada_config.mqtt.host = host
        if port is not None:
            scada_config.mqtt.port = port
        if username is not None:
            scada_config.mqtt.username = username
        if password is not None:
            scada_config.mqtt.password = SecretStr(password)
        if use_tls is not None:
            scada_config.mqtt.tls.use_tls = use_tls
    else:
        rich.print(
            f"Scada with name {name} [red][bold]already exists. Doing nothing.[/red][/bold]\n"
        )
        rich.print(
            "Use --update to update the existing configuration or --force to overwrite it.\n"
        )
        raise typer.Exit(5)
    if len(current_config.config.scadas) == 1 or default:
        current_config.config.default_scada = name
    rich.print(f"Updating config file {current_config.paths.admin_config_path}")
    with current_config.paths.admin_config_path.open(mode="w") as f:
        f.write(current_config.config.model_dump_json(indent=2))


def version_callback(value: bool):
    if value:
        rich.print(f"GridWorks Scada Admin Client, version {__version__}")
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
