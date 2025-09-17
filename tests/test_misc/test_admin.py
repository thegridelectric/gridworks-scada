from typing import Any

import pytest
from gwadmin.cli import watch_settings
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

@pytest.mark.asyncio
async def test_admin_basic(request: pytest.FixtureRequest) -> None:
    """This test just verifies that clis can execute dry-runs and help without
    exception. It does not attempt to test content of execution."""
    settings = ScadaSettings(admin=AdminLinkSettings(enabled=True))
    layout = House0Layout.load(settings.paths.hardware_layout)
    print(layout.scada_g_node_alias)
    async with ScadaLiveTest(
            request=request,
            start_child1=True,
            child_app_settings=settings
    ) as h:
        await h.await_for(
            h.child_to_parent_link.active_for_send,
            "ERROR waiting link active_for_send",
        )
        settings = watch_settings(
            target=layout.scada_g_node_alias,
            env_file="",
            verbose=0,
        )
        settings.link.tls.use_tls = False
        relays_app = RelaysApp(settings=settings)
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
            await pilot.click("#relays_table")
            await pilot.press(*(["down"] * 13))
            assert_relay_table_row(
                relays_app, [18, "Zone1 Main Ops", "RelayOpen", "CloseRelay", "⚫️"]
            )

            # toggle the relay
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

