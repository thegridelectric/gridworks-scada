from typing import Any

import pytest
import rich

from gwproactor.config.mqtt import TLSInfo
from textual.widgets import Button
from textual.widgets import Input

from gwadmin.cli import get_admin_config
from gwadmin.config import AdminMQTTClient
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
        exp_button_title = f"E[underline]n[/underline]ergize"
        exp_label_icon = "🔴"
    else:
        exp_button_title = f"Dee[underline]n[/underline]ergize"
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
            verbose=0,
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
    """Set a relay and verify we see the set take effect."""
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
            verbose=0,
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
            #await pilot.press("enter")

            table = relays_app.query_one("#dacs_table", DataTable)
            success = await h.await_for(
                lambda: int(table.get_row_at(table.cursor_row)[1]) == 31,
                "ERROR wait for admin to dac update",
                timeout=10,
                raise_timeout=False,
            )
            if not success:
                print_dacs(relays_app, "Scada did not report DAC change")
                raise AssertionError(f"Timeout waiting for admin to dac update")
            # verify change is as expected
            assert_dac_table_row(
                relays_app,
                ["Dist", "31"],
                31,
                tag="dac value set"
            )


