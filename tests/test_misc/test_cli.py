import shutil
import textwrap
from pathlib import Path
from typing import Any

from gwproactor_test import copy_keys
from gwproactor_test.certs import uses_tls
from typer.testing import CliRunner

from gwproactor.config import Paths

from actors.config import ScadaSettings
from cli import app as scada_cli_app
from scada2_app import Scada2App
from scada_app import ScadaApp
from tests.conftest import TEST_HARDWARE_LAYOUT_PATH
from tests.atn.atn_app import AtnApp
from tests.atn.cli import app as atn_cli_app
from tests.atn.atn_config import AtnSettings

runner = CliRunner()


def test_gws_cli_completes() -> None:
    """This test just verifies that clis can execute dry-runs and help without
    exception. It does not attempt to test content of execution."""
    settings = ScadaSettings()
    if uses_tls(settings):
        copy_keys("scada", settings)
    for app_type in [ScadaApp, Scada2App]:
        paths = Paths(name=app_type.paths_name())
        paths.mkdirs(parents=True, exist_ok=True)
        shutil.copyfile(Path(TEST_HARDWARE_LAYOUT_PATH), paths.hardware_layout)
    env_path = Path(settings.paths.config_dir).absolute() / ".env"
    with env_path.open("w") as env_file:
        env_file.write("SCADA_IS_SIMULATED=true")
    command: list[str]
    for command in [
        [],
        ["admin"],
        ["admin", "config"],
        ["admin", "demo"],
        ["admin", "demo", "actions", "--help"],
        ["admin", "demo", "stopwatch", "--help"],
        ["admin", "demo", "switch", "--help"],
        ["admin", "watch", "--help"],
        ["admin", "watchex", "--help"],
        ["config", "--env-file", str(env_path)],
        ["layout"],
        ["layout", "mktest", "--help"],
        ["layout", "show", "--env-file", str(env_path)],
        ["run", "--dry-run", "--env-file", str(env_path)],
        ["run-s2", "--dry-run"],
    ]:
        result = runner.invoke(scada_cli_app, command)
        result_str = (
            f"exit code: {result.exit_code}\n"
            f"\t{result!s} from command\n"
            f"\t<gws {' '.join(command)}> with output\n"
            f"{textwrap.indent(result.output, '        ')}"
        )
        assert result.exit_code == 0, result_str

def test_atn_cli_completes(request: Any) -> None:
    """This test just verifies that clis can execute dry-runs and help without
    exception. It does not attempt to test content of execution."""
    settings = AtnSettings()
    if uses_tls(settings):
        copy_keys("atn", settings)
    for app_type in [AtnApp]:
        paths = Paths(name=app_type.paths_name())
        paths.mkdirs(parents=True, exist_ok=True)
        shutil.copyfile(Path(TEST_HARDWARE_LAYOUT_PATH), paths.hardware_layout)
    env_path = Path(settings.paths.config_dir).absolute() / ".env"
    env_path.touch(exist_ok=True)
    command: list[str]
    for command in [
        [],
        ["config", "--env-file", str(env_path)],
        ["run", "--dry-run", "--env-file", str(env_path)],
    ]:
        result = runner.invoke(atn_cli_app, command)
        result_str = (
            f"exit code: {result.exit_code}\n"
            f"\t{result!s} from command\n"
            f"\t<atn cli {' '.join(command)}> with output\n"
            f"{textwrap.indent(result.output, '        ')}"
        )
        assert result.exit_code == 0, result_str
