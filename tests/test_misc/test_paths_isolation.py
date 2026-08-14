"""Pins the app-construction behavior the experiment-window harness's
paths-root isolation depends on: every construction path re-applies
cls.paths_name() (get_settings ends with .with_paths, and make_app_for_cli
rebuilds settings through cls()), so env-file and argument overrides of
paths.name are silently DISCARDED. The 2026-08-12 window leaked an event to
prod through the shared event dir that way. The only override that holds is
subclassing paths_name() — the window harness's WindowScadaApp mechanism.
If either test fails, gwproactor's behavior changed: revisit the window
harness before the next spruce window."""

from pathlib import Path

import pytest

from gwproactor.app import App
from scada_app import ScadaApp

SPRUCE_LAYOUT = Path(__file__).parent.parent / "config" / "gw.nolan.layout.json"
SPRUCE_OPS = (
    Path(__file__).parent.parent
    / "config"
    / "gw.nolan.operational.params.json"
)


class ExperimentScadaApp(ScadaApp):
    @classmethod
    def paths_name(cls) -> str:
        return "scada-experiment"


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    env = tmp_path / "test.env"
    env.write_text(
        "SCADA_IS_SIMULATED=true\n"
        f'SCADA_PATHS__HARDWARE_LAYOUT="{SPRUCE_LAYOUT}"\n'
        f'SCADA_OPERATIONAL_PARAMS_PATH="{SPRUCE_OPS}"\n'
        'SCADA_PATHS__NAME="somewhere-else"\n'
    )
    return env


def _build(app_class: type[ScadaApp], env_file: Path) -> App:
    settings = app_class.get_settings(env_file=env_file)
    # conftest exports the Nolan fixture's ops path into the process env,
    # which beats the dotenv line; point at spruce's on the object
    settings.paths.operational_params = SPRUCE_OPS
    return App.make_app_for_cli.__func__(
        app_class,
        app_settings=settings,
        env_file=env_file,
        add_screen_handler=False,
    )


def test_paths_name_overrides_are_discarded(env_file: Path) -> None:
    """Env-file SCADA_PATHS__NAME and get_settings(paths_name=...) both lose
    to cls.paths_name() — the trap, pinned."""
    app = _build(ScadaApp, env_file)
    assert str(app.settings.paths.name) == "scada"
    settings = ScadaApp.get_settings(env_file=env_file, paths_name="also-lost")
    settings.paths.operational_params = SPRUCE_OPS
    rebuilt = App.make_app_for_cli.__func__(
        ScadaApp,
        app_settings=settings,
        env_file=env_file,
        add_screen_handler=False,
    )
    assert str(rebuilt.settings.paths.name) == "scada"


def test_paths_name_subclass_override_holds(env_file: Path) -> None:
    """The window harness's mechanism: only the classmethod survives."""
    app = _build(ExperimentScadaApp, env_file)
    assert str(app.settings.paths.name) == "scada-experiment"
    assert "scada-experiment" in str(app.settings.paths.event_dir)
    assert "scada-experiment" in str(app.settings.paths.log_dir)
