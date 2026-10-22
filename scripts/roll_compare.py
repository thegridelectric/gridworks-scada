"""Compare a box's layout pair with the committed tlayouts JSON.

Used by scripts/roll.sh. A layout matches only byte for byte. An
operational-params file matches when everything but its DispatchHold
block is equal, because the scada writes that block itself (the cold
latch sets ServiceContractBroken; an operator hold sets OperatorHold).

A second pi runs scada2, which senses through the nodes under the `s2`
actor and nothing else, so its file is compared on the sensed part
alone: the s2 node and the nodes in its hierarchy, their components,
those components' attribute classes, and the data channels those nodes
capture. The rest of the file is the primary scada's and may differ.

Usage: roll_compare.py layout|ops|sensed <committed.json> <box.json>
Exit 0 on a match; exit 1 with the differing paths on stdout otherwise.
"""

import json
import sys
from pathlib import Path

SCADA_WRITTEN = "DispatchHold"
SECONDARY_SCADA = "s2"


def flatten(value, prefix=""):
    """Dotted path -> leaf value; lists compare as one leaf."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out.update(flatten(item, f"{prefix}.{key}" if prefix else key))
        return out
    return {prefix: json.dumps(value, sort_keys=True)}


def differing_paths(committed: dict, box: dict, ignore_top: str | None) -> list[str]:
    a = flatten(committed)
    b = flatten(box)
    paths = sorted(set(a) | set(b))
    return [
        p for p in paths
        if a.get(p) != b.get(p)
        and not (ignore_top and p.split(".")[0] == ignore_top)
    ]


def layout_matches(committed: bytes, box: bytes) -> bool:
    return committed == box


def ops_differences(committed: dict, box: dict) -> list[str]:
    return differing_paths(committed, box, SCADA_WRITTEN)


def sensed_part(layout: dict, scada: str = SECONDARY_SCADA) -> dict:
    """What the given scada senses in a layout, keyed by name or id."""
    nodes = {
        n["Name"]: n
        for n in layout["ShNodes"]
        if n["Name"] == scada
        or (n.get("ActorHierarchyName") or "").startswith(f"{scada}.")
    }
    component_ids = {n["ComponentId"] for n in nodes.values() if n.get("ComponentId")}
    components = {
        c["ComponentId"]: c
        for key, items in layout.items() if key.endswith("Components")
        for c in items if c["ComponentId"] in component_ids
    }
    cac_ids = {c["ComponentAttributeClassId"] for c in components.values()}
    cacs = {
        c["ComponentAttributeClassId"]: c
        for key, items in layout.items() if key.endswith("Cacs")
        for c in items if c["ComponentAttributeClassId"] in cac_ids
    }
    channels = {
        c["Name"]: c for c in layout["DataChannels"] if c.get("CapturedByNodeName") in nodes
    }
    return {"ShNodes": nodes, "Components": components, "Cacs": cacs, "DataChannels": channels}


def sensed_differences(committed: dict, box: dict) -> list[str]:
    return differing_paths(sensed_part(committed), sensed_part(box), None)


def main(argv: list[str]) -> int:
    kind, committed_path, box_path = argv[1], Path(argv[2]), Path(argv[3])
    if kind == "layout":
        if layout_matches(committed_path.read_bytes(), box_path.read_bytes()):
            return 0
        committed = json.loads(committed_path.read_text())
        box = json.loads(box_path.read_text())
        diffs = differing_paths(committed, box, None)
        print("\n".join(diffs) if diffs else "same content, different bytes (key order or whitespace)")
        return 1
    if kind in ("ops", "sensed"):
        committed = json.loads(committed_path.read_text())
        box = json.loads(box_path.read_text())
        compare = ops_differences if kind == "ops" else sensed_differences
        diffs = compare(committed, box)
        if not diffs:
            return 0
        print("\n".join(diffs))
        return 1
    print(f"unknown kind {kind}; layout, ops or sensed", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
