"""sema_to_dc — assemble the authored artifacts into the dc layout the scada loads.

The gen machinery lives in tlayouts (the authoring home, on the sema snapshot);
scada consumes its two authored artifacts per home:

    gw.house0.layout.json ⊕ gw.house0.operational.params.json
        ──ops_and_sema_to_dc──▶ runtime House0Sema ──sema_to_dc──▶ House0Dc

`assemble_runtime_layout` splices each channel's capture.tuning back onto its
component's ConfigList entry (bare components get their ConfigList rebuilt from
the tunings of the channels they capture), carrying the two assembly checks:
assembly coverage (the ops file covers every channel the static layout
declares) and the poll floor (PollPeriodMs ≥ the device type's MinPollPeriodMs;
the layout owns the floor, the ops file owns PollPeriodMs).

The forward diff-and-adopt oracle (`diff_against_fixture` / `main`)
canon-compares the assembled layout against its frozen `tests/config/<home>.json`
fixture — a review aid, not a strict gate (the strict gate is behavioral: the
sim-run boot).

    python sema_to_dc.py [home] [authored_dir]   # default: oak ../../tlayouts/output/oak
"""

import copy
import json
import sys
from pathlib import Path
from typing import Any

from gwsproto.data_classes.house_0_layout import House0Layout as House0Dc
from gwsproto.named_types import House0Layout as House0Sema
from gwsproto.named_types import NolanLayout

CONFIG_DIR = Path(__file__).resolve().parent.parent / "tests" / "config"

# The authored static artifact names its sema layout type; dispatch on it.
SEMA_LAYOUT_BY_TYPENAME: dict[str, type[House0Sema] | type[NolanLayout]] = {
    "gw.house0.layout": House0Sema,
    "gw.nolan.layout": NolanLayout,
}

_CAPTURE_FIELDS = (
    "PollPeriodMs",
    "CapturePeriodS",
    "AsyncCapture",
    "AsyncCaptureDelta",
)


def assemble_runtime_layout(
    static: dict[str, Any], ops: dict[str, Any]
) -> dict[str, Any]:
    """Splice the ops file's capture.tuning entries onto the static layout's
    components, producing the runtime-shaped layout dict. Raises on the two
    assembly-validity failures (coverage, poll floor)."""
    static = copy.deepcopy(static)
    tuning_by_channel = {t["ChannelName"]: t for t in ops["CaptureTuningList"]}

    # assembly coverage: ops covers every channel the static layout declares
    declared = {c["Name"] for c in static.get("DataChannels") or []}
    missing = sorted(declared - set(tuning_by_channel))
    if missing:
        raise ValueError(
            f"assembly coverage failed: no capture.tuning for channel(s) {missing}"
        )

    # poll floor: layout owns MinPollPeriodMs (via the device type); ops owns PollPeriodMs
    floor_by_device_type = {
        dt["DeviceType"]: dt["MinPollPeriodMs"]
        for dt in static.get("DeviceTypes") or []
        if "MinPollPeriodMs" in dt
    }

    nodes_by_component: dict[str, list[str]] = {}
    for node in static.get("ShNodes") or []:
        cid = node.get("ComponentId")
        if cid:
            nodes_by_component.setdefault(cid, []).append(node["Name"])

    for comp in static.get("Components") or []:
        capturing = set(nodes_by_component.get(comp["ComponentId"], []))
        captured = [
            c["Name"]
            for c in static.get("DataChannels") or []
            if c["CapturedByNodeName"] in capturing
        ]
        floor = floor_by_device_type.get(comp.get("DeviceType"))
        for name in captured:
            poll = tuning_by_channel[name].get("PollPeriodMs")
            if floor is not None and poll is not None and poll < floor:
                raise ValueError(
                    f"poll floor failed: channel '{name}' PollPeriodMs {poll} < "
                    f"MinPollPeriodMs {floor} of device type {comp['DeviceType']}"
                )
        if "ConfigList" in comp:
            # specialty configs: merge the capture fields back onto each entry
            for cfg in comp["ConfigList"]:
                tuning = tuning_by_channel.get(cfg["ChannelName"])
                if tuning is None:
                    continue  # coverage above guards declared channels
                for field in _CAPTURE_FIELDS:
                    if field in tuning:
                        cfg[field] = tuning[field]
        else:
            # bare component: rebuild ConfigList from the tunings of the
            # channels its node(s) capture
            comp["ConfigList"] = [copy.deepcopy(tuning_by_channel[n]) for n in captured]
    return static


def ops_and_sema_to_dc(static_path: Path, ops_path: Path) -> House0Dc:
    """Assemble the two authored artifacts and load the dc House0Layout."""
    static = json.loads(Path(static_path).read_text())
    ops = json.loads(Path(ops_path).read_text())
    assembled = assemble_runtime_layout(static, ops)
    sema = SEMA_LAYOUT_BY_TYPENAME[assembled["TypeName"]].model_validate(assembled)
    return House0Dc.load_dict(sema_to_layout_dict(sema))


def sema_to_layout_dict(sema: House0Sema | NolanLayout) -> dict[str, Any]:
    """Build the layout dict the data class can load. Components/cacs are
    regrouped into the typed keys load_dict expects."""
    layout: dict[str, Any] = {}
    # GNodes back to the three named entries, reconstructed FROM the sema GNodes
    # (keyed by GNodeClass).
    by_class = {
        "Scada": "MyScadaGNode",
        "TerminalAsset": "MyTerminalAssetGNode",
        "LeafTransactiveNode": "MyLeafTransactiveNodeGNode",
    }
    for gn in sema.GNodes or []:
        key = by_class.get(gn.GNodeClass, "MyLeafTransactiveNodeGNode")
        layout[key] = gn.model_dump(by_alias=True, exclude_none=True, mode="json")
    if sema.Hydronic is not None:
        layout["Hydronic"] = sema.Hydronic.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )
    layout["ShNodes"] = [
        n.model_dump(by_alias=True, exclude_none=True, mode="json")
        for n in (sema.ShNodes or [])
    ]
    layout["DataChannels"] = [
        c.model_dump(by_alias=True, exclude_none=True, mode="json")
        for c in (sema.DataChannels or [])
    ]
    layout["DerivedChannels"] = [
        c.model_dump(by_alias=True, exclude_none=True, mode="json")
        for c in (sema.DerivedChannels or [])
    ]

    em, ads, other = [], [], []
    for c in sema.Components or []:
        d = c.model_dump(by_alias=True, exclude_none=True, mode="json")
        if c.TypeName == "electric.meter.component.gt":
            em.append(d)
        elif c.TypeName == "ads111x.based.component.gt":
            ads.append(d)
        else:
            other.append(d)
    (
        layout["ElectricMeterComponents"],
        layout["Ads111xBasedComponents"],
        layout["OtherComponents"],
    ) = em, ads, other

    layout["DeviceTypes"] = [
        c.model_dump(by_alias=True, exclude_none=True, mode="json")
        for c in (sema.DeviceTypes or [])
    ]
    return layout


def sema_to_dc(sema: House0Sema) -> House0Dc:
    """Project an axiom-valid runtime-shaped House0Layout to the dc the scada loads."""
    return House0Dc.load_dict(sema_to_layout_dict(sema))


def _canon(layout: dict) -> dict:
    """Sort every collection by a stable key so the comparison is order-INSENSITIVE.
    List order in a layout is just historical authoring/load order — not
    semantically meaningful — so the gen is free to emit its own canonical order;
    equivalence is content + id, not position. (A frozen fixture adopts the gen's
    order on migration.)"""

    def key(r: dict) -> str:
        return str(
            r.get("Name")
            or r.get("Alias")
            or r.get("GNodeId")
            or r.get("DeviceType")
            or f"{r.get('TypeName', '')}|{r.get('DisplayName', '')}|{r.get('ComponentId', '')}"
        )

    for k, v in layout.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            layout[k] = sorted(v, key=key)
    return layout


def diff_against_fixture(name: str, authored_dir: Path) -> int:
    """Review aid: canon-compare the assembled tlayouts artifacts against the
    frozen tests/config/<name>.json fixture and print the per-collection diff.
    The diff is the adopt worklist (gen omissions vs stale-fixture gaps), not a
    strict gate."""
    layout_paths = sorted(p for p in authored_dir.glob("gw.*.layout.json"))
    if len(layout_paths) != 1:
        raise ValueError(
            f"expected exactly one gw.*.layout.json in {authored_dir}; found {layout_paths}"
        )
    static_path = layout_paths[0]
    ops_path = authored_dir / "gw.house0.operational.params.json"

    static = json.loads(static_path.read_text())
    ops = json.loads(ops_path.read_text())
    assembled = assemble_runtime_layout(static, ops)
    sema = SEMA_LAYOUT_BY_TYPENAME[assembled["TypeName"]].model_validate(assembled)
    gen_layout = sema_to_layout_dict(sema)

    print(f"== ops_and_sema_to_dc({name}) loads? ==")
    try:
        House0Dc.load_dict(copy.deepcopy(gen_layout))
        print("  assembled dc: LOADS OK")
    except Exception as e:  # noqa: BLE001
        print(f"  assembled dc: FAILS -> {type(e).__name__}: {str(e)[:200]}")
        return 1

    frozen = json.loads((CONFIG_DIR / f"{name}.json").read_text())
    gen_c = _canon(copy.deepcopy(gen_layout))
    fro_c = _canon(copy.deepcopy(frozen))
    print(f"== assembled-dc vs frozen {name}.json (canon, order-insensitive) ==")
    print(f"  {'KEY':38} {'gen':>6} {'frozen':>7}")
    diffs = 0
    for k in sorted(set(gen_c) | set(fro_c)):
        gv, fv = gen_c.get(k), fro_c.get(k)
        gn = len(gv) if isinstance(gv, list) else ("-" if gv is None else "obj")
        fn = len(fv) if isinstance(fv, list) else ("-" if fv is None else "obj")
        flag = "" if gn == fn else "  <-- DIFF"
        if flag:
            diffs += 1
        print(f"  {k:38} {str(gn):>6} {str(fn):>7}{flag}")
    print(f"== {diffs} collection-count diff(s) — review and adopt ==")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    name = argv[0] if argv else "oak"
    default_dir = (
        Path(__file__).resolve().parent.parent.parent / "tlayouts" / "output" / name
    )
    authored_dir = Path(argv[1]) if len(argv) > 1 else default_dir
    return diff_against_fixture(name, authored_dir)


if __name__ == "__main__":
    raise SystemExit(main())
