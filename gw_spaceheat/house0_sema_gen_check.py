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
from house0_sema_gen import (
    AdsChannelSpec,
    FlowSpec,
    House0SemaGenConfig,
    PwrChannelSpec,
    TankSpec,
    sema_gen,
    strip_relay_idx,
)
from layout_roundtrip import _DUMP, _report_diff


def _to_new_convention(layout: dict) -> dict:
    """Rename a frozen (old-named) target to the new convention in place: drop
    the trailing relay-index on relay-state channel names, wherever they appear
    (DataChannels[].Name and component ConfigList[].ChannelName). UUIDs untouched
    — this is the names migration the gen targets, applied to the comparison set."""
    for ch in layout.get("DataChannels") or []:
        ch["Name"] = strip_relay_idx(ch["Name"])
    for comp in layout.get("Components") or []:
        for cfg in comp.get("ConfigList") or []:
            if "ChannelName" in cfg:
                cfg["ChannelName"] = strip_relay_idx(cfg["ChannelName"])
    return layout

SCADA_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCADA_DIR.parent / "tests" / "config"


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
            hubitat_host="192.168.0.1",
            hubitat_maker_api_id=1,
            hubitat_access_token="64a43fa4-0eb9-478f-ad2e-374bc9b7e51f",
            hubitat_mac="34:E1:D1:82:22:22",
            zone_device_ids=[1],
        ),
        CONFIG_DIR / "house0-layout.json",
    ),
    "oak": (
        House0SemaGenConfig(
            scada_display_name="OAK SCADA",
            zone_list=["living-rm", "garage", "gear-rm", "upstairs"],
            critical_zone_list=["living-rm", "gear-rm", "upstairs"],
            zone_kwh_per_deg_f_list=[1, 0, 0, 1],
            total_store_tanks=3,
            strategy="House0",
            use_sieg_loop=False,
            sieg_loop_plumbed=False,
            primary_flow_source="Measured",
            web_server_port=8000,
            relay_i2c_address_list=[0x20, 0x23],
            tank_kind="real",
            tanks=[
                TankSpec("pico_64ac21", 1.002, 127),   # buffer
                TankSpec("pico_62ab21", 1.047, -347),  # tank1
                TankSpec("pico_31ac21", 1.03, -160),   # tank2
                TankSpec("pico_16a321", 1.021, -104),  # tank3
            ],
            hubitat_host="192.168.0.200",
            hubitat_maker_api_id=2,
            hubitat_access_token="a8232144-abe9-4eed-bcfd-8f182600b8e7",
            hubitat_mac="34:e1:d1:81:37:82",
            zone_device_ids=[108, 112, 110, 113],
            dfr_initial_volts_times_100=[50, 50, 0],
            power_meter_kind="egauge",
            egauge_modbus_host="eGauge6074.local",
            egauge_modbus_port=502,
            egauge_hwuid="BP01954",
            power_meter_channels=[
                PwrChannelSpec("hp-odu-pwr", "hp-odu", 9000, 300, 6000, True),
                PwrChannelSpec("hp-idu-pwr", "hp-idu", 9002, 300, 4000, True),
                PwrChannelSpec("dist-pump-pwr", "dist-pump", 9010, 2, 10, False),
                PwrChannelSpec("primary-pump-pwr", "primary-pump", 9012, 2, 10, False),
                PwrChannelSpec("store-pump-pwr", "store-pump", 9014, 2, 10, False),
                PwrChannelSpec("oil-boiler-pwr", "oil-boiler", 9008, 2, 10, False),
                PwrChannelSpec("zone1-living-rm-whitewire-pwr", "zone1-living-rm-whitewire", 9016, 2, 10, False),
                PwrChannelSpec("zone2-garage-whitewire-pwr", "zone2-garage-whitewire", 9020, 2, 10, False),
                PwrChannelSpec("zone3-gear-rm-whitewire-pwr", "zone3-gear-rm-whitewire", 9022, 2, 10, False),
                PwrChannelSpec("zone4-upstairs-whitewire-pwr", "zone4-upstairs-whitewire", 9018, 2, 10, False),
            ],
            ads_hwuid="102",
            ads_open_voltage_by_ads=[5.05, 5.05, 5.05],
            ads_channels=[
                AdsChannelSpec("dist-swt", 1),
                AdsChannelSpec("dist-rwt", 2),
                AdsChannelSpec("hp-lwt", 3),
                AdsChannelSpec("hp-ewt", 4),
                AdsChannelSpec("store-hot-pipe", 5),
                AdsChannelSpec("buffer-hot-pipe", 7),
                AdsChannelSpec("buffer-cold-pipe", 8),
            ],
            flow_meters=[
                FlowSpec("primary", "pico_436531", "1026"),
                FlowSpec("store", "pico_836d31", "1027"),
                FlowSpec("dist", "pico_974532", "1025"),
            ],
        ),
        CONFIG_DIR / "oak.json",
    ),
}


def check(name: str) -> int:
    config, reference = CONFIGS[name]
    dc = House0Dc.load(str(reference))
    target, gaps = dc_to_sema(dc)
    if gaps:
        print(f"dc -> sema gaps in reference: {gaps}")
    target_d = _canon(_to_new_convention(target.model_dump(**_DUMP)))
    got_d = _canon(sema_gen(config, reference).model_dump(**_DUMP))

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
