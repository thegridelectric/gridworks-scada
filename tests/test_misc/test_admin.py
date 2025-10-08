import json
import os
import textwrap
from typing import Any
from typing import Optional

import pytest
import rich
from gwproactor.config import Paths

from gwproactor.config.mqtt import TLSInfo
from click.testing import Result as ClickResult
from pydantic import SecretStr
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Select
from typer.testing import CliRunner

from gwadmin.cli import app as gwa
from gwadmin.cli import get_admin_config
from gwadmin.cli import __version__ as gwa_version
from gwadmin.config import AdminConfig
from gwadmin.config import AdminMQTTClient
from gwadmin.config import AdminPaths
from gwadmin.config import CurrentAdminConfig
from gwadmin.config import ScadaConfig
from gwadmin.watch.clients.constrained_mqtt_client import ConstrainedMQTTClient
from gwadmin.watch.relay_app import RelaysApp
from gwadmin.watch.widgets.mqtt import MqttState
from gwadmin.watch.widgets.relay_toggle_button import RelayToggleButton
from gwsproto.data_classes.house_0_layout import House0Layout
from textual.containers import HorizontalGroup
from textual.widgets import DataTable

from actors.config import AdminLinkSettings
from actors.config import ScadaSettings
from tests.utils.scada_live_test_helper import ScadaLiveTest


runner = CliRunner()

def get_admin_verbosity(request: pytest.FixtureRequest, default: int = 0) -> int:
    option = request.config.getoption("--admin-verbosity")
    if option is None:
        return default
    return int(option)


def assert_relay_table_row(app: RelaysApp, exp_row: list[Any], tag: str = ""):
    table = app.query_one("#relays_table", DataTable)
    got_row = table.get_row_at(table.cursor_row)
    tag_str = "" if not tag else f"<{tag}>"
    err_str = (
        f"Unexpected relay row in relays table. {tag_str}\n"
        f"  exp: {exp_row}\n"
        f"  got: {got_row}\n"
        "\nDid the relay table change?\n"
    )
    assert got_row == exp_row, err_str
    button_container = app.query_one("#relay_toggle_button_container", HorizontalGroup)
    assert button_container.border_title == f"Relay {exp_row[0]}: {exp_row[1]}", (
        "Unexpected relay button container title"
    )
    button  = app.query_one("#relay_toggle_button", RelayToggleButton)
    if exp_row[-1] == "⚫️":
        exp_button_title = "E[underline]n[/underline]ergize"
        exp_label_icon = "🔴"
    else:
        exp_button_title = "Dee[underline]n[/underline]ergize"
        exp_label_icon = "⚫️"
    assert button.border_title == exp_button_title, f"Unexpected toggle button border title {tag_str}"
    assert button.label == f"{exp_label_icon} {exp_row[-2]}", f"Unexpected toggle button label {tag_str}"

def assert_dac_table_row(
        app: RelaysApp,
        exp_row: list[Any],
        exp_input: int | None = None,
        tag: str = ""
):
    table = app.query_one("#dacs_table", DataTable)
    exp_row[1] = int(exp_row[1])
    got_row = table.get_row_at(table.cursor_row)
    got_row[1] = int(got_row[1])
    tag_str = "" if not tag else f"<{tag}>"
    err_str = (
        f"Unexpected dac row in dacs table. {tag_str}\n"
        f"  exp: {exp_row}\n"
        f"  got: {got_row}\n"
    )
    assert got_row == exp_row, err_str
    dac_input = app.query_one("#dac_value_input", Input)
    if exp_input is None:
        assert dac_input.value == ""
    else:
        assert int(dac_input.value) == int(exp_input)
    exp_border_title = f"DAC: {exp_row[0]}"
    box = app.query_one("#dac_control_container", HorizontalGroup)
    assert box.border_title == exp_border_title, f"Unexpected toggle button border title {tag_str}"
    exp_button_label = f"Set {exp_row[0]} to {exp_input if exp_input is not None else ''}"
    button  = app.query_one("#send_dac_button", Button)
    assert str(button.label) == exp_button_label, f"Unexpected toggle button label {tag_str}"
    exp_disabled = not(isinstance(exp_input, int) and 0 <= exp_input <= 100)
    assert button.disabled == exp_disabled, f"Unexpected toggle button disbaled. Got {button.disabled} {tag_str}"

def print_dacs(app: RelaysApp, tag = ""):
    table = app.query_one("#dacs_table", DataTable)
    rich.print(f"Dacs table  ({tag})")
    for i in range(len(table.rows)):
        rich.print(f"  {i}: {'[red]*[/red]' if i == table.cursor_row else ' '}  {table.get_row_at(i)}")

def _result_str(result: ClickResult, command: list[str], tag: str = "") -> str:
    tag_str = "" if not tag else f"\t<{tag}>\n"
    return (
        f"{tag_str}"
        f"exit code: {result.exit_code}\n"
        f"\t{result!s} from command\n"
        f"\t<gwa {' '.join([str(entry) for entry in command])}> with output\n"
        f"{textwrap.indent(result.output, '        ')}"
    )

def _gwa(command: str | list[str], exp_exit: int = 0, tag: str = "") -> ClickResult:
    if isinstance(command, str):
        command = [command]
    result = runner.invoke(gwa, command, env=os.environ)
    assert result.exit_code == exp_exit, _result_str(result, command, tag=tag)
    return result

def _check_config(exp: AdminConfig, paths: Optional[AdminPaths] = None) -> AdminConfig:
    if paths is None:
        paths = AdminPaths(name="admin")
    with paths.admin_config_path.open("r") as f:
        file_loaded = AdminConfig.model_validate_json(f.read())
    command_loaded = CurrentAdminConfig.model_validate_json(
            _gwa(
                [
                    "config",
                    "--json",
                    "--config-name",
                    paths.name
                ]
            ).output
        )
    assert command_loaded.config.model_dump_json(indent=2) == file_loaded.model_dump_json(indent=2)
    assert exp.model_dump_json(indent=2) == command_loaded.config.model_dump_json(indent=2)
    return command_loaded.config

def _make_scadas(short2long: dict[str, str]) -> dict[str, ScadaSettings]:
    _gwa("mkconfig")
    short2settings = {}
    for short_name, long_name in short2long.items():
        _gwa(["add-scada", short_name, "--long-name", long_name])
        layout = House0Layout.load(Paths().hardware_layout)
        layout.layout["MyScadaGNode"]["Alias"] = long_name
        short2settings[short_name] = ScadaSettings(
            admin=AdminLinkSettings(enabled=True)
        ).with_paths_name(short_name)
        short2settings[short_name].paths.mkdirs()
        with short2settings[short_name].paths.hardware_layout.open("w") as f:
            f.write(json.dumps(layout.layout, indent=2, sort_keys=True))
    return short2settings

async def _await_scada_connected(
    lt: ScadaLiveTest,
    app: RelaysApp,
    short_name: str,
    long_name: str,
    timeout: float = 10,
):
    mqtt_state = app.query_one("#mqtt_state", MqttState)
    await lt.await_for(
        lambda: mqtt_state.mqtt_state == ConstrainedMQTTClient.States.active,
        "ERROR wait for admin mqtt state active",
        timeout=timeout,
    )
    await lt.await_for(
        lambda: app.layout_received(),
        "ERROR wait for admin to receive a layout (from pear)",
        timeout=timeout,
    )
    await lt.await_for(
        lambda: app.snapshot_received(),
        "ERROR wait for admin to receive a snapshot (from pear)",
        timeout=timeout,
    )
    assert short_name in app.sub_title
    assert long_name in app.sub_title
    select_box = app.query_one("#select_scada", Select)
    assert select_box.value == short_name


@pytest.mark.asyncio
async def test_admin_relay_set(request: pytest.FixtureRequest) -> None:
    """Set a relay and verify we see the set take effect."""
    settings = ScadaSettings(admin=AdminLinkSettings(enabled=True))
    layout = House0Layout.load(settings.paths.hardware_layout)
    async with ScadaLiveTest(
            request=request,
            start_child1=True,
            child_app_settings=settings
    ) as h:
        await h.await_for(
            h.child_to_parent_link.active_for_send,
            "ERROR waiting link active_for_send",
        )
        curr_admin_config = get_admin_config(
            env_file="",
            verbose=get_admin_verbosity(request),
        )
        curr_admin_config.curr_scada = "local"
        curr_admin_config.config.scadas["local"] = ScadaConfig(
            mqtt=AdminMQTTClient(tls=TLSInfo(use_tls=False)),
            long_name=layout.scada_g_node_alias,
        )
        relays_app = RelaysApp(settings=curr_admin_config)
        async with relays_app.run_test() as pilot:
            # Wait for admin to connect to scada
            mqtt_state = relays_app.query_one("#mqtt_state", MqttState)
            await h.await_for(
                lambda: mqtt_state.mqtt_state == ConstrainedMQTTClient.States.active,
                "ERROR wait for admin mqtt state active",
            )
            await h.await_for(
                lambda: relays_app.layout_received(),
                "ERROR wait for admin to receive a layout",
            )
            await h.await_for(
                lambda: relays_app.snapshot_received(),
                "ERROR wait for admin to receive a snapshot",
            )

            # select the relay table and a relay row scada won't change
            # by itself
            await pilot.press("r")
            await pilot.press(*(["down"] * 13))
            assert_relay_table_row(
                relays_app, [18, "Zone1 Main Ops", "RelayOpen", "CloseRelay", "⚫️"]
            )

            # set the dac the relay
            await pilot.press("n")
            # wait for it to change
            table = relays_app.query_one("#relays_table", DataTable)
            await h.await_for(
                lambda: table.get_row_at(table.cursor_row)[2] == "RelayClosed",
                "ERROR wait for admin to receive a relay closed",
            )
            # verify change is as expected
            assert_relay_table_row(
                relays_app,
                [18, "Zone1 Main Ops", "RelayClosed", "OpenRelay", "🔴"]
            )

@pytest.mark.asyncio
async def test_admin_dac_set(request: pytest.FixtureRequest) -> None:
    """Set a dac and verify we see the set take effect."""
    settings = ScadaSettings(admin=AdminLinkSettings(enabled=True))
    layout = House0Layout.load(settings.paths.hardware_layout)
    async with ScadaLiveTest(
            request=request,
            start_child1=True,
            child_app_settings=settings,
    ) as h:
        await h.await_for(
            h.child_to_parent_link.active_for_send,
            "ERROR waiting link active_for_send",
        )
        curr_admin_config = get_admin_config(
            env_file="",
            verbose=get_admin_verbosity(request),
        )
        curr_admin_config.curr_scada = "local"
        curr_admin_config.config.scadas["local"] = ScadaConfig(
            mqtt=AdminMQTTClient(tls=TLSInfo(use_tls=False)),
            long_name=layout.scada_g_node_alias,
        )
        relays_app = RelaysApp(settings=curr_admin_config)
        async with relays_app.run_test() as pilot:
            # Wait for admin to connect to scada
            mqtt_state = relays_app.query_one("#mqtt_state", MqttState)
            await h.await_for(
                lambda: mqtt_state.mqtt_state == ConstrainedMQTTClient.States.active,
                "ERROR wait for admin mqtt state active",
            )
            await h.await_for(
                lambda: relays_app.layout_received(),
                "ERROR wait for admin to receive a layout",
            )
            await h.await_for(
                lambda: relays_app.snapshot_received(),
                "ERROR wait for admin to receive a snapshot",
            )

            # select the dac table
            await pilot.press("d")
            assert relays_app.focused.id == "dacs_table"
            table = relays_app.query_one("#dacs_table", DataTable)
            assert_dac_table_row(
                relays_app, ["Dist", 20], tag="dac default row"
            )

            # select the input box
            await pilot.press("\t")
            assert relays_app.focused.id == "dac_value_input"
            # enter 31
            await pilot.press("3", "1")
            assert_dac_table_row(
                relays_app,["Dist", 20], 31, tag="dac value entered"
            )

            # set the dac
            await pilot.press("\t")
            assert relays_app.focused.id == "send_dac_button"
            await pilot.press("enter")

            table = relays_app.query_one("#dacs_table", DataTable)
            success = await h.await_for(
                lambda: int(table.get_row_at(table.cursor_row)[1]) == 31,
                "ERROR wait for admin to dac update",
                timeout=10,
                raise_timeout=False,
            )
            if not success:
                print_dacs(relays_app, "Scada did not report DAC change")
                raise AssertionError("Timeout waiting for admin to dac update")
            # verify change is as expected
            assert_dac_table_row(
                relays_app,
                ["Dist", "31"],
                31,
                tag="dac value set"
            )

@pytest.mark.asyncio
async def test_admin_scada_select(request: pytest.FixtureRequest) -> None:
    short2long = {
        "pear": "metropolis.electric.pear",
        "carrot": "springfield.electric.carrot",
        "sea-pickle": "atlantis.thermal.sea-pickle",
    }
    short2settigns = _make_scadas(short2long)
    curr_admin_config = CurrentAdminConfig.model_validate_json(
        _gwa(["config", "--json"]).output
    )
    curr_admin_config.curr_scada = curr_admin_config.config.default_scada

    curr_admin_config.config.verbosity = get_admin_verbosity(request)
    async with ScadaLiveTest(
        request=request,
        child_app_settings=short2settigns["pear"],
        start_child=True,
    ) as hpear:
        await hpear.await_for(
            hpear.child_to_parent_link.active_for_send,
            "ERROR waiting pear scada to be active_for_send",
        )
        async with ScadaLiveTest(
            request=request,
            child_app_settings=short2settigns["carrot"],
            start_child=True,
        ) as hcarrot:
            await hcarrot.await_for(
                hcarrot.child_to_parent_link.active_for_send,
                "ERROR waiting carrot scada to be active_for_send",
            )

            relays_app = RelaysApp(settings=curr_admin_config)
            async with relays_app.run_test() as pilot:
                # Verify we connect to the default scada
                await _await_scada_connected(
                    hpear, relays_app, short_name="pear", long_name=short2long["pear"],
                    timeout=3,
                )

                # Set the dac control so we can verify it is cleared when
                # switching scada
                await pilot.press("d")
                assert relays_app.focused.id == "dacs_table"
                assert_dac_table_row(relays_app, ["Dist", 20], tag="dac default row")
                await pilot.press("\t")
                assert relays_app.focused.id == "dac_value_input"
                await pilot.press("3", "1")
                assert_dac_table_row(
                    relays_app, ["Dist", 20], 31, tag="dac value entered"
                )

                # Select the next scada, carrot, and verify we connect
                await pilot.click("#select_scada")
                await pilot.press("enter")
                await pilot.press("down")
                await pilot.press("down")
                await pilot.press("enter")
                await _await_scada_connected(
                    hpear, relays_app, short_name="carrot", long_name=short2long["carrot"],
                    timeout=3,
                )
                assert relays_app.query_one("#dac_value_input", Input).value == ""
                assert relays_app.query_one("#send_dac_button", Button).disabled is True

                # Set the dac control so we can verify it is cleared when
                # switching scada
                await pilot.press("d")
                assert relays_app.focused.id == "dacs_table"
                assert_dac_table_row(relays_app, ["Dist", 20], tag="dac default row")
                await pilot.press("\t")
                assert relays_app.focused.id == "dac_value_input"
                await pilot.press("3", "1")
                assert_dac_table_row(
                    relays_app, ["Dist", 20], 31, tag="dac value entered"
                )

                # Select the last scada, sea-pickle, which isn't running, and
                # verify the the relays and dacs tables empty.
                await pilot.click("#select_scada")
                await pilot.press("enter")
                await pilot.press("down")
                await pilot.press("down")
                await pilot.press("enter")
                assert relays_app.query_one("#select_scada", Select).value == "sea-pickle"
                await hpear.await_for(
                    lambda: len(relays_app.query_one("#relays_table", DataTable).rows) == 0,
                    "ERROR waiting for relay table to empty",
                )
                assert relays_app.query_one(
                    "#relay_toggle_button",
                    Button
                ).disabled is True
                assert relays_app.query_one(
                    "#relay_toggle_button_container",
                    HorizontalGroup
                ).border_title == ""
                await hpear.await_for(
                    lambda: len(relays_app.query_one("#dacs_table", DataTable).rows) == 0,
                    "ERROR waiting for dac table to empty",
                )
                assert relays_app.query_one("#dac_value_input", Input).value == ""
                assert relays_app.query_one("#send_dac_button", Button).disabled is True





def test_admin_version() -> None:
    """Verify 'gwa version' produces expected results."""
    result = _gwa(["--version"])
    assert gwa_version in result.output

def test_admin_config_file() -> None:
    paths = AdminPaths(name="admin")
    result = _gwa(["config-file"])
    exp = str(paths.admin_config_path)
    got = result.output.strip().replace("\n", "")
    assert exp == got

def test_admin_empty_config() -> None:
    result = _gwa(["config", "--json"])
    exp = AdminConfig()
    got = AdminConfig.model_validate_json(result.output)
    assert exp == got

def test_admin_mkconfig() -> None:
    _gwa(["mkconfig"])
    exp = AdminConfig()
    with AdminPaths(name="admin").admin_config_path.open("r") as f:
        got = AdminConfig.model_validate_json(f.read())
    assert exp == got

def test_admin_mkconfig_force() -> None:
    # Create a config
    _gwa(["mkconfig"])
    curr_config = CurrentAdminConfig(
        paths=AdminPaths(name="admin"),
    )
    curr_config.config = _check_config(curr_config.config)

    # Change it
    curr_config.config.verbosity += 1
    curr_config.save_config()
    _check_config(curr_config.config)

    # Try to overwrite it
    result = _gwa(["mkconfig"], 4)
    assert "Doing nothing" in result.output
    assert curr_config.config == _check_config(curr_config.config)

    # Force overwrite it
    _gwa(["mkconfig", "--force"])
    _check_config(AdminConfig())


def test_admin_config() -> None:
    # Create a default config
    _gwa("mkconfig")
    _check_config(AdminConfig())

    # Increase verbosity and save
    _gwa(["config", "--save", "-v"])

    # Verify the change
    _check_config(AdminConfig(verbosity=20))

def test_admin_add_scada() -> None:
    # Create a default config
    _gwa("mkconfig")
    _check_config(AdminConfig())

    scada_name = "pear"
    scfg = ScadaConfig(
        enabled=False,
        mqtt=AdminMQTTClient(
            host="foo",
            port=1,
            username="bar",
            password=SecretStr("bla"),
            tls=TLSInfo(use_tls=True)
        ),
        long_name="baz",
    )

    # Add a scada
    _gwa([
        "add-scada",
        scada_name,
        "--no-enabled",
        "--long-name", scfg.long_name,
        "--host", scfg.mqtt.host,
        "--port", scfg.mqtt.port,
        "--username", scfg.mqtt.username,
        "--password", scfg.mqtt.password.get_secret_value(),
        "--use-tls",
    ])

    exp = AdminConfig(default_scada=scada_name, scadas={scada_name: scfg})
    _check_config(exp)

    # Try to overwrite
    new_long_name = "BLA.BLA.BLA"
    _gwa(
        [
            "add-scada",
            scada_name,
            "--long-name", new_long_name,
        ],
        exp_exit=5,
    )

    # Verify scada config did not change
    _check_config(exp)

    # Update
    _gwa(
        [
            "add-scada",
            scada_name,
            "--long-name", new_long_name,
            "--update"
        ],
    )

    # Verify the change took
    exp.scadas[scada_name].long_name = new_long_name
    _check_config(exp)

