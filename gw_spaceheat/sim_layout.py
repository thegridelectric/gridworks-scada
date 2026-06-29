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
GNODE_KEYS = ("MyScadaGNode", "MyTerminalAssetGNode", "MyLeafTransactiveNodeGNode")
DEV_UNIVERSE = "d1"


def _rewrite_universe(alias: str, universe: str) -> str:
    parts = alias.split(".")
    parts[0] = universe
    return ".".join(parts)


def devify_aliases(layout: dict[str, Any], universe: str = DEV_UNIVERSE) -> dict[str, Any]:
    """Rewrite every GNodeAlias into the dev universe so a simulated layout is
    coherent with the dev broker (the universe guardrail rejects a `hw1.*` sim
    layout on the `d1` dev broker). Touches the three GNode aliases plus the
    `TerminalAssetAlias` carried on each data/derived channel."""
    for key in GNODE_KEYS:
        gnode = layout.get(key)
        if isinstance(gnode, dict) and gnode.get("Alias"):
            gnode["Alias"] = _rewrite_universe(gnode["Alias"], universe)
    for channel_key in ("DataChannels", "DerivedChannels"):
        for channel in layout.get(channel_key, []):
            if channel.get("TerminalAssetAlias"):
                channel["TerminalAssetAlias"] = _rewrite_universe(
                    channel["TerminalAssetAlias"], universe
                )
    return layout


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

    # A simulated layout must live in a dev (or hybrid) universe, never production
    # — dev-ify the aliases so it's coherent with the dev broker it boots on.
    devify_aliases(layout)
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
