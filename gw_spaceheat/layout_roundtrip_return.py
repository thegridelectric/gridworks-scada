"""Hack: scada side of the layout round-trip.

Reads a layout JSON instance (a Sema layout type the gwta side sent), decodes it
through gwsproto, re-encodes it, and writes it back. Invoked by
gridworks-terminalasset/layout_roundtrip.py using the scada venv python.

    python layout_roundtrip_return.py <infile.json> <outfile.json>
"""

import json
import sys

from gwsproto.named_types import House0Layout, SimpleSimLayout

# The layout types use short local class names (not the TypeName pascalized).
LAYOUT_BY_TYPENAME = {
    "gw.house0.layout": House0Layout,
    "gw1.simple.sim.layout": SimpleSimLayout,
}


def class_for(type_name: str) -> type:
    return LAYOUT_BY_TYPENAME[type_name]


def main() -> int:
    infile, outfile = sys.argv[1], sys.argv[2]
    with open(infile) as f:
        data = json.load(f)

    cls = class_for(data["TypeName"])
    obj = cls.model_validate(data)
    returned = obj.model_dump(by_alias=True, exclude_none=True, mode="json")

    with open(outfile, "w") as f:
        json.dump(returned, f, indent=2)

    print(f"scada: decoded + re-encoded {data['TypeName']} via {cls.__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
