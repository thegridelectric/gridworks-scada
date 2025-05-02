from pathlib import Path

import rich
from gwproactor_test import copy_keys
from gwproactor_test.certs import uses_tls

import show_layout
from actors.config import ScadaSettings


def test_show_layout_on_test_layout():
    settings = ScadaSettings()
    if uses_tls(settings):
        copy_keys("scada", settings)
    layout_path = Path(__file__).parent.parent / "config" / "hardware-layout.json"
    errors = show_layout.main(["-l", str(layout_path)])
    if errors:
        rich.print(errors)
    assert not errors
