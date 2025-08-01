from pathlib import Path

import rich
from gwproactor_test import copy_keys
from gwproactor_test.certs import uses_tls

import show_layout
from actors.config import ScadaSettings


def test_show_layout_on_test_layout(tmp_path):
    env_path = tmp_path / ".env"
    with open(env_path, "w") as f:
        f.write("SCADA_IS_SIMULATED=true")
    settings = ScadaSettings()
    if uses_tls(settings):
        copy_keys("scada", settings)
    layout_path = Path(__file__).parent.parent / "config" / "hardware-layout.json"
    errors = show_layout.main(
        [
            "-e", str(env_path),
            "-l", str(layout_path),
            "-r"
         ]
    )
    if errors:
        rich.print(errors)
    assert not errors
