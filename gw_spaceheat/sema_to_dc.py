"""sema_to_dc — assemble the authored artifacts into the dc layout the scada loads.

The gen machinery lives in tlayouts (the authoring home, on the sema snapshot);
scada consumes its two authored artifacts per home:

    gw.house0.layout.json ⊕ gw.house0.operational.params.json
        ──ops_and_sema_to_dc──▶ runtime House0Sema ──sema_to_dc──▶ House0Dc

`assemble_runtime_layout` validates the two assembly checks: assembly coverage
(the ops file covers every channel the static layout declares) and the poll
floor (PollPeriodMs ≥ the device type's MinPollPeriodMs; the layout owns the
floor, the ops file owns PollPeriodMs). Capture tuning is never spliced onto
components — it stays on the ops artifact's CaptureTuningList, threaded
through to the runtime layout as HardwareLayout.capture_tuning_by_channel.

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

from actors.config import DEFAULT_OPS_PARAMS_FILE
from gwsproto.data_classes.house_0_layout import House0Layout as House0Dc
from gwsproto.named_types import House0Layout as House0Sema
from gwsproto.named_types import (
    House0OperationalParams,
    NolanLayout,
    NolanOperationalParams,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "tests" / "config"

# The authored static artifact names its sema layout type; dispatch on it.
SEMA_LAYOUT_BY_TYPENAME: dict[str, type[House0Sema] | type[NolanLayout]] = {
    "gw.house0.layout": House0Sema,
    "gw.nolan.layout": NolanLayout,
}

OperationalParams = House0OperationalParams | NolanOperationalParams

# The ONLY layout ⊕ operational-params pairings a scada may boot. A home's
# operational params are authored against its layout family: the House0 word
# carries the store/optimization knobs (SeasonalStorageMode, HpTurnOnMinutes,
# ShortCycleBuffer, LoadOverestimationPercent, OilBoilerBackup, HorizonHours)
# that House0 control reads, and the Nolan word carries the cooling-season TOU
# schedule (OnPeakWindows, HeldCircuitPositions) that Nolan control reads.
# A crossed pair decodes but then starves whichever control path it feeds, so
# the pairing is checked at load and a mismatch refuses the boot outright.
APPROVED_PAIRS: dict[str, str] = {
    "gw.house0.layout": "gw.house0.operational.params",
    "gw.nolan.layout": "gw.nolan.operational.params",
}

SEMA_OPS_BY_TYPENAME: dict[str, type[OperationalParams]] = {
    "gw.house0.operational.params": House0OperationalParams,
    "gw.nolan.operational.params": NolanOperationalParams,
}


def check_approved_pair(layout_type_name: str, ops_type_name: str) -> None:
    """Refuse any layout ⊕ operational-params pairing outside APPROVED_PAIRS.
    Raises ValueError naming both words and the one partner that is allowed."""
    expected = APPROVED_PAIRS.get(layout_type_name)
    if expected is None:
        raise ValueError(
            f"Layout word {layout_type_name!r} has no approved operational-params "
            f"partner. Approved pairs: {APPROVED_PAIRS}."
        )
    if ops_type_name != expected:
        raise ValueError(
            f"Mismatched artifact pair: layout {layout_type_name!r} SHALL be paired "
            f"with {expected!r}, got operational params {ops_type_name!r}. "
            f"Approved pairs: {APPROVED_PAIRS}. Scada will not start."
        )


def decode_operational_params(ops: dict[str, Any]) -> OperationalParams:
    """Decode the operational-params artifact through its own family's word."""
    type_name = ops.get("TypeName")
    ops_cls = SEMA_OPS_BY_TYPENAME.get(str(type_name))
    if ops_cls is None:
        raise ValueError(
            f"Operational params TypeName {type_name!r} is not a known "
            f"operational-params word. Known: {sorted(SEMA_OPS_BY_TYPENAME)}."
        )
    return ops_cls.model_validate(ops)

def assemble_runtime_layout(
    static: dict[str, Any], ops: dict[str, Any]
) -> dict[str, Any]:
    """Validate the static layout against the ops file's capture.tuning
    coverage and poll floor; return the static layout unchanged (capture
    tuning is never spliced onto components — see module docstring)."""
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
    return static


def ops_and_sema_to_dc(
    static_path: Path, ops_path: Path, **load_kwargs: Any
) -> House0Dc:
    """Assemble the two authored artifacts and load the dc House0Layout. The
    pair SHALL be approved (see APPROVED_PAIRS); a mismatch raises."""
    static = json.loads(Path(static_path).read_text())
    ops = json.loads(Path(ops_path).read_text())
    check_approved_pair(str(static.get("TypeName")), str(ops.get("TypeName")))
    assembled = assemble_runtime_layout(static, ops)
    sema = SEMA_LAYOUT_BY_TYPENAME[assembled["TypeName"]].model_validate(assembled)
    layout_dict = sema_to_layout_dict(sema)
    layout_dict["CaptureTuningList"] = ops.get("CaptureTuningList", [])
    dc = House0Dc.load_dict(layout_dict, **load_kwargs)
    dc.layout_type_name = sema.TypeName
    return dc


def load_layout(
    layout_path: Path | str,
    ops_path: Path | str,
    **load_kwargs: Any,
) -> House0Dc:
    """Load a runtime layout from the home's two authored artifacts. BOTH paths
    are passed in the same way — callers take them from settings.paths
    (hardware_layout and operational_params); neither filename is constructed
    here. The static artifact SHALL be sema-authored (its TypeName names a sema
    layout word) and the pair SHALL be approved (see APPROVED_PAIRS). Every app
    and tool loads through here."""
    type_name = json.loads(Path(layout_path).read_text()).get("TypeName")
    if type_name not in SEMA_LAYOUT_BY_TYPENAME:
        raise ValueError(
            f"{layout_path} has TypeName {type_name!r}; a layout must be "
            f"sema-authored, naming one of {sorted(SEMA_LAYOUT_BY_TYPENAME)}. "
            "Generate the layout ⊕ operational-params pair in tlayouts."
        )
    return ops_and_sema_to_dc(Path(layout_path), Path(ops_path), **load_kwargs)


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
    ops_path = authored_dir / DEFAULT_OPS_PARAMS_FILE

    static = json.loads(static_path.read_text())
    ops = json.loads(ops_path.read_text())
    assembled = assemble_runtime_layout(static, ops)
    sema = SEMA_LAYOUT_BY_TYPENAME[assembled["TypeName"]].model_validate(assembled)
    gen_layout = sema_to_layout_dict(sema)
    gen_layout["CaptureTuningList"] = ops.get("CaptureTuningList", [])

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
