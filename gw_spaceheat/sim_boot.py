"""sim-run boot — the behavioral safety net (hardware-layout-pass-one, OPS-407).

Boots a real `ScadaApp` standalone against the dev rabbit broker (`gw-dev-rabbit`,
MQTT on `localhost:1885` via the Rabbit MQTT plugin), `is_simulated=True`, with no
LTN parent so the scada sits in LocalControl. It runs the actor tree for a bounded
number of seconds and reports how many channel values populated.

This is the EDD reproducer behind the `sim-run` spoke: confidence comes from the
scada actually booting + running its device code paths on a real broker, not from
in-process tests. The entry mirrors `cli.py run` (`ScadaApp.main`) but is *bounded*
— it drives `proactor.run_forever()` under `asyncio.wait_for`, so the harness
returns cleanly instead of running forever.

    cd gw_spaceheat && ./venv/bin/python sim_boot.py [layout.json] [seconds]

Requires the `gw-dev-rabbit` container up (creds in `gridworks-scada/.env`).
"""

import asyncio
import json
import sys
from pathlib import Path

from gwsproto.data_classes.house_0_layout import House0Layout

from scada_app import ScadaApp
from actors.config import DEFAULT_OPS_PARAMS_FILE
from sim_layout import simulate_sensors

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ENV = str(REPO / ".env")
DEFAULT_LAYOUT = str(REPO / "tests" / "config" / "gw.nolan.layout.json")
DEFAULT_SECONDS = 8


def build_app(layout_path: str, env_file: str = DEFAULT_ENV) -> ScadaApp:
    """Construct + instantiate a standalone simulated ScadaApp from a real layout.

    The real layout is transformed in-memory (`simulate_sensors`: pico-fed sensors
    → SimSensorActor, aliases dev-ified) so it self-generates on the dev broker and
    is universe-coherent with it — no on-disk sim fixture needed."""
    settings = ScadaApp.get_settings(env_file=env_file)
    settings.is_simulated = True
    # the ops artifact sits beside the layout being booted, which is not
    # settings.paths.hardware_layout here
    settings.paths.operational_params = (
        Path(layout_path).parent / DEFAULT_OPS_PARAMS_FILE
    )
    sim = simulate_sensors(json.loads(Path(layout_path).read_text()))
    app = ScadaApp(app_settings=settings, layout=House0Layout.load_dict(sim))
    app.instantiate()
    app.assert_universe_coherence()  # the simulated layout is dev-universe; must match localhost (d1)
    return app


async def _run_bounded(app: ScadaApp, seconds: int) -> None:
    try:
        await asyncio.wait_for(app.proactor.run_forever(), timeout=seconds)
    except asyncio.TimeoutError:
        app.proactor.stop()


def boot_and_run(
    layout_path: str = DEFAULT_LAYOUT,
    seconds: int = DEFAULT_SECONDS,
    env_file: str = DEFAULT_ENV,
) -> tuple[ScadaApp, dict, dict]:
    """Boot the scada, run `seconds`, and return (app, all channel values, non-null subset)."""
    app = build_app(layout_path, env_file)
    asyncio.run(_run_bounded(app, seconds))
    vals = dict(app.scada._data.latest_channel_values)
    non_null = {k: v for k, v in vals.items() if v is not None}
    return app, vals, non_null


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    layout = argv[0] if argv else DEFAULT_LAYOUT
    seconds = int(argv[1]) if len(argv) > 1 else DEFAULT_SECONDS
    print(f"== boot {Path(layout).name} for {seconds}s on gw-dev-rabbit (is_simulated) ==")
    app, vals, non_null = boot_and_run(layout, seconds)
    print(f"  layout: {len(app.hardware_layout.nodes)} nodes")
    print(f"  latest_channel_values: {len(vals)} channels, {len(non_null)} non-null")
    print(f"  sample: {dict(list(non_null.items())[:6])}")
    print("  BOOT OK" if non_null else "  booted but no channels populated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
