import shutil
import textwrap
from pathlib import Path

from gwproactor_test import copy_keys
from gwproactor_test.certs import uses_tls
from typer.testing import CliRunner

from gwproactor.config import Paths
from gwadmin.cli import app as gwa_cli

from actors.config import ScadaSettings
from cli import app as scada_cli_app
from scada2_app import Scada2App
from scada_app import ScadaApp
from atn_app import AtnApp
from tests.conftest import TEST_HARDWARE_LAYOUT_PATH

runner = CliRunner()

admin_commands = [
    [],
    ["add-scada", "--help"],
    ["config"],
    ["config-file"],
    ["mkconfig", "--help"],
    ["watch", "--help"],
]

def test_gws_cli_completes() -> None:
    """This test just verifies that clis can execute dry-runs and help without
    exception. It does not attempt to test content of execution."""
    settings = ScadaSettings()
    if uses_tls(settings):
        copy_keys("scada", settings)
    for app_type in [ScadaApp, Scada2App, AtnApp]:
        paths = Paths(name=app_type.paths_name())
        paths.mkdirs(parents=True, exist_ok=True)
        shutil.copyfile(Path(TEST_HARDWARE_LAYOUT_PATH), paths.hardware_layout)
    env_path = Path(settings.paths.config_dir).absolute() / ".env"
    with env_path.open("w") as env_file:
        env_file.write("SCADA_IS_SIMULATED=true")
    for command in [
        [],
        ["atn"],
        ["atn", "config", "--env-file", str(env_path)],
        ["atn", "run", "--help"],
        ["atn", "run", "--dry-run", "--env-file", str(env_path)],
        ["config", "--env-file", str(env_path)],
        ["layout"],
        ["layout", "mktest", "--help"],
        ["layout", "show", "--env-file", str(env_path)],
        ["run", "--dry-run", "--env-file", str(env_path)],
        ["run", "--help", "--env-file", str(env_path)],
        ["run-s2", "--dry-run"],
        ["run-s2", "--help"],
    ]:
        result = runner.invoke(scada_cli_app, command)
        result_str = (
            f"exit code: {result.exit_code}\n"
            f"\t{result!s} from command\n"
            f"\t<gws {' '.join(command)}> with output\n"
            f"{textwrap.indent(result.output, '        ')}"
        )
        assert result.exit_code == 0, result_str
    result = runner.invoke(scada_cli_app, ["admin"])
    assert result.exit_code == 1, result.output

def test_gwa_cli_completes() -> None:
    """This test just verifies that clis can execute dry-runs and help without
    exception. It does not attempt to test content of execution."""
    settings = ScadaSettings()
    env_path = Path(settings.paths.config_dir).absolute() / ".env"
    with env_path.open("w") as env_file:
        env_file.write("SCADA_IS_SIMULATED=true")
    command: list[str]
    for command in admin_commands:
        result = runner.invoke(gwa_cli, command)
        result_str = (
            f"exit code: {result.exit_code}\n"
            f"\t{result!s} from command\n"
            f"\t<gws {' '.join(command)}> with output\n"
            f"{textwrap.indent(result.output, '        ')}"
        )
        assert result.exit_code == 0, result_str
