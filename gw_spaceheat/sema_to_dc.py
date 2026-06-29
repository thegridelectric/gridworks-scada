"""sema_to_dc — project an authored gw.house0.layout sema object to the dc layout
the running scada loads.

This is the forward partner of `sema_gen` (house0_sema_gen.py): sema is the
authored source of truth, the dc `House0Layout` is a generated output.

    per-home config ──sema_gen──▶ gw.house0.layout (sema) ──sema_to_dc──▶ House0Dc

`sema_to_layout_dict` builds the layout dict `House0Layout.load_dict` expects
(regrouping Components into the typed keys); `sema_to_dc` loads it. The forward
diff-and-adopt oracle (`diff_against_fixture` / `main`) canon-compares a
generated layout against its frozen `tests/config/<home>.json` fixture — a review
aid, not a strict gate (the strict gate is behavioral: the sim-run boot).

    python sema_to_dc.py [home]   # default: oak
"""

import copy
import json
import sys
from typing import Any

from gwsproto.data_classes.house_0_layout import House0Layout as House0Dc
from gwsproto.named_types import House0Layout as House0Sema


def sema_to_layout_dict(sema: House0Sema) -> dict[str, Any]:
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
    for gn in (sema.GNodes or []):
        key = by_class.get(gn.GNodeClass, "MyLeafTransactiveNodeGNode")
        layout[key] = gn.model_dump(by_alias=True, exclude_none=True, mode="json")
    if sema.Hydronic is not None:
        layout["Hydronic"] = sema.Hydronic.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )
    layout["ShNodes"] = [n.model_dump(by_alias=True, exclude_none=True, mode="json") for n in (sema.ShNodes or [])]
    layout["DataChannels"] = [c.model_dump(by_alias=True, exclude_none=True, mode="json") for c in (sema.DataChannels or [])]
    layout["DerivedChannels"] = [c.model_dump(by_alias=True, exclude_none=True, mode="json") for c in (sema.DerivedChannels or [])]

    em, ads, other = [], [], []
    for c in (sema.Components or []):
        d = c.model_dump(by_alias=True, exclude_none=True, mode="json")
        if c.TypeName == "electric.meter.component.gt":
            em.append(d)
        elif c.TypeName == "ads111x.based.component.gt":
            ads.append(d)
        else:
            other.append(d)
    layout["ElectricMeterComponents"], layout["Ads111xBasedComponents"], layout["OtherComponents"] = em, ads, other

    layout["DeviceTypes"] = [
        c.model_dump(by_alias=True, exclude_none=True, mode="json")
        for c in (sema.DeviceTypes or [])
    ]
    return layout


def sema_to_dc(sema: House0Sema) -> House0Dc:
    """Project an axiom-valid sema House0Layout to the dc House0Layout the scada loads."""
    return House0Dc.load_dict(sema_to_layout_dict(sema))


def diff_against_fixture(name: str) -> int:
    """Review aid: canon-compare sema_to_dc(sema_gen(<name>)) against the frozen
    tests/config/<name>.json fixture and print the per-collection diff. The diff is
    the adopt worklist (gen omissions vs stale-fixture gaps), not a strict gate."""
    # Imported lazily so the projection functions above carry no gen/test coupling.
    from house0_sema_gen import sema_gen
    from house0_sema_gen_check import CONFIGS, CONFIG_DIR, _canon

    config, reference = CONFIGS[name]
    gen_layout = sema_to_layout_dict(sema_gen(config, reference))

    print(f"== sema_to_dc(sema_gen({name})) loads? ==")
    try:
        House0Dc.load_dict(copy.deepcopy(gen_layout))
        print("  generated dc: LOADS OK")
    except Exception as e:  # noqa: BLE001
        print(f"  generated dc: FAILS -> {type(e).__name__}: {str(e)[:200]}")
        return 1

    frozen = json.loads((CONFIG_DIR / f"{name}.json").read_text())
    gen_c = _canon(copy.deepcopy(gen_layout))
    fro_c = _canon(copy.deepcopy(frozen))
    print(f"== generated-dc vs frozen {name}.json (canon, order-insensitive) ==")
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
    return diff_against_fixture(argv[0] if argv else "oak")


if __name__ == "__main__":
    raise SystemExit(main())
