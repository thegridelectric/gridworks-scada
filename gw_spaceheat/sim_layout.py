"""Build a *simulated* House0 layout from a real one: swap each pico-fed sensor
actor (tanks, flow, BTU, multipurpose ADS) for a `SimSensorActor` backed by a
bare `sim.sensor.component.gt`, so the scada's sensor channels populate from the
self-generating actor — no pico, no HTTP POST. DataChannels are untouched:
`CapturedByNodeName` still points at the same nodes, which now self-generate.

PowerMeter is intentionally NOT swapped — it already self-generates in sim via
the `GridworksSimPowerMeter` driver.

    python sim_layout.py <real-layout.json> <out-sim-layout.json>
"""

import copy
import json
import sys
from pathlib import Path
from typing import Any

PICO_FED_SENSOR_ACTORS = {
    "ApiTankModule",
    "ApiFlowModule",
    "ApiBtuMeter",
    "MultipurposeSensor",
}
COMPONENT_LIST_KEYS = (
    "OtherComponents",
    "Ads111xBasedComponents",
    "ElectricMeterComponents",
)


def simulate_sensors(layout: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `layout` with every pico-fed sensor actor replaced by a
    self-generating SimSensorActor + bare sim.sensor.component.gt component."""
    layout = copy.deepcopy(layout)

    sim_component_ids: set[str] = set()
    for node in layout.get("ShNodes", []):
        if node.get("ActorClass") in PICO_FED_SENSOR_ACTORS:
            node["ActorClass"] = "SimSensorActor"
            if node.get("ComponentId"):
                sim_component_ids.add(node["ComponentId"])

    sim_components = []
    for key in COMPONENT_LIST_KEYS:
        kept = []
        for comp in layout.get(key, []):
            if comp.get("ComponentId") in sim_component_ids:
                sim_components.append(
                    {
                        "ComponentId": comp["ComponentId"],
                        "DisplayName": comp.get("DisplayName", "Sim Sensor"),
                        "DeviceType": "GridworksSimSensor",
                        # Preserve the original ConfigList so the dc
                        # ComponentDataChannelBijection still holds (every captured
                        # DataChannel stays referenced by its component).
                        "ConfigList": comp.get("ConfigList", []),
                        "TypeName": "sim.sensor.component.gt",
                        "Version": "000",
                    }
                )
            else:
                kept.append(comp)
        layout[key] = kept
    layout["OtherComponents"] = layout.get("OtherComponents", []) + sim_components
    return layout


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    src, dst = argv
    out = simulate_sensors(json.loads(Path(src).read_text()))
    Path(dst).write_text(json.dumps(out, indent=2))
    n = sum(1 for nd in out["ShNodes"] if nd.get("ActorClass") == "SimSensorActor")
    print(f"wrote {dst}: {n} SimSensorActor nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
