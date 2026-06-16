"""EDD harness for the sema-native House0 gen (hardware-layout-pass-one, Task a).

Validates the gen against the dc path for a fleet shape:

    sema_gen(config)  ==  dc_to_sema(House0Dc.load(reference))

Both sides are dumped with the same options the round-trip uses
(`by_alias, exclude_none, mode=json`) and diffed field-by-field. The printed
diff IS the worklist: each remaining gap is a builder the gen has not emitted yet
(or a field it emits differently). Generate -> observe the gap -> close it.

    python house0_sema_gen_check.py [house0]

Run with the scada venv (gw_spaceheat/venv).
"""

import sys
from pathlib import Path

from gwsproto.data_classes.house_0_layout import House0Layout as House0Dc
from house0_bijection import dc_to_sema
from house0_sema_gen import House0SemaGenConfig, sema_gen
from layout_roundtrip import _DUMP, _report_diff

SCADA_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCADA_DIR.parent / "tests" / "config"


# Each entry: config built to mirror its on-disk reference layout exactly.
CONFIGS: dict[str, tuple[House0SemaGenConfig, Path]] = {
    "house0": (
        House0SemaGenConfig(
            scada_display_name="Little Orange House Main Scada",
            zone_list=["main"],
            critical_zone_list=["main"],
            zone_kwh_per_deg_f_list=[1],
            total_store_tanks=1,
            strategy="House0",
            use_sieg_loop=False,
            sieg_loop_plumbed=False,
            primary_flow_source="Measured",
        ),
        CONFIG_DIR / "house0-layout.json",
    ),
}


def check(name: str) -> int:
    config, reference = CONFIGS[name]
    dc = House0Dc.load(str(reference))
    target, gaps = dc_to_sema(dc)
    if gaps:
        print(f"dc -> sema gaps in reference: {gaps}")
    target_d = target.model_dump(**_DUMP)
    got_d = sema_gen(config, reference).model_dump(**_DUMP)

    if got_d == target_d:
        print(f"GEN OK [{name}]: sema_gen == dc_to_sema(load({reference.name}))")
        return 0
    # quick collection-count summary, then the field diff
    for key in ("GNodes", "ShNodes", "DataChannels", "DerivedChannels", "Components", "DeviceTypes"):
        t, g = target_d.get(key) or [], got_d.get(key) or []
        if len(t) != len(g):
            print(f"  count {key}: target={len(t)} gen={len(g)}")
    print(f"GEN MISMATCH [{name}]:")
    _report_diff(got_d, target_d)
    return 1


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "house0"
    sys.exit(check(name))
