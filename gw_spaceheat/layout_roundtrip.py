"""Scada-originated layout round-trip: a real dc layout, out to gwta and back.

This harness STARTS in scada. It loads a layout JSON file (e.g. tests/config/
maple.json) as a gwsproto **data class**, converts it to the `gw.house0.layout`
**Sema** type via the house0 bijection, and SENDS that to gwta, which RETURNS it
decoded + re-encoded through the gwta snapshot. We then decode the returned bytes
back through gwsproto and confirm they match what scada sent.

A green run proves scada and gwta agree on the layout type's wire contract, end
to end from a real deployed-style layout:

    maple.json -> dataclass -> sema -> gwta -> scada

The loop this serves: edit the layout type in Sema -> snapshot to gwta -> hand-
port to gwsproto -> run this script.

    python layout_roundtrip.py [tests/config/maple.json]

Run with the scada venv (gw_spaceheat/venv); it shells out to the gwta venv for
the return leg.
"""

import json
import subprocess
import sys
from pathlib import Path

from gwsproto.data_classes.house_0_layout import House0Layout as House0Dc
from gwsproto.named_types import House0Layout as House0Sema
from house0_bijection import dc_to_sema

SHARED = Path("/tmp/gw_layout_roundtrip")
SCADA_DIR = Path(__file__).resolve().parent                       # gw_spaceheat
TA = SCADA_DIR.parent.parent / "gridworks-terminalasset"
TA_PY = TA / ".venv" / "bin" / "python"
TA_RETURN = TA / "layout_roundtrip_return.py"

DEFAULT_LAYOUT = SCADA_DIR.parent / "tests" / "config" / "maple.json"

_DUMP = dict(by_alias=True, exclude_none=True, mode="json")


def _report_diff(sent: dict, got: dict) -> None:
    for key in sorted(set(sent) | set(got)):
        if sent.get(key) == got.get(key):
            continue
        sv, gv = sent.get(key), got.get(key)
        # lists of named records (channels, components, …): diff by Name/field
        if isinstance(sv, list) and isinstance(gv, list) and sv and isinstance(sv[0], dict):
            s = {r.get("Name", i): r for i, r in enumerate(sv)}
            g = {r.get("Name", i): r for i, r in enumerate(gv)}
            for name in sorted(set(s) | set(g), key=str):
                sr, gr = s.get(name, {}), g.get(name, {})
                for f in sorted(set(sr) | set(gr)):
                    if sr.get(f) != gr.get(f):
                        print(f"  {key}[{name}].{f}: sent={sr.get(f)!r} got={gr.get(f)!r}")
        else:
            print(f"  {key}: sent={sv!r} got={gv!r}")


def main() -> int:
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LAYOUT
    SHARED.mkdir(parents=True, exist_ok=True)
    outbound_path = SHARED / "outbound.json"
    returned_path = SHARED / "returned.json"

    # SCADA: dc layout JSON -> data class -> sema gw.house0.layout
    dc = House0Dc.load(str(arg))
    sema, gaps = dc_to_sema(dc)
    if gaps:
        print(f"dc -> sema gaps: {gaps}")
    outbound = sema.model_dump(**_DUMP)
    outbound_path.write_text(json.dumps(outbound, indent=2))
    print(f"scada: {arg.name} -> {outbound['TypeName']} -> {outbound_path}")

    # gwta RETURNS it (decode + re-encode through the gwta snapshot), in its venv.
    subprocess.run(
        [str(TA_PY), str(TA_RETURN), str(outbound_path), str(returned_path)],
        check=True,
    )

    # SCADA: decode the returned bytes through gwsproto and compare to what we sent.
    returned = json.loads(returned_path.read_text())
    redecoded = House0Sema.model_validate(returned).model_dump(**_DUMP)
    if redecoded == outbound:
        print(
            f"ROUND-TRIP OK: {outbound['TypeName']} survived "
            "scada -> gwta -> scada unchanged."
        )
        return 0
    print(f"ROUND-TRIP MISMATCH for {outbound['TypeName']}:")
    _report_diff(outbound, redecoded)
    return 1


if __name__ == "__main__":
    sys.exit(main())
