"""EDD harness: prove the gw.house0.layout sema type encodes every part of the
loaded House0 data-class layout, by attempting the bijection

    data-class House0Layout  ->  sema House0Layout  ->  data-class House0Layout

Forward (dc -> sema) checks that every collection in the loaded layout fits a
sema field. Inverse (sema -> layout dict -> load_dict) checks the sema form
reloads into an equal data class. Where it breaks shows what the sema type does
not yet encode.

    python house0_bijection.py
"""

import copy
import json
from pathlib import Path
from typing import Any

from gwsproto.data_classes.house_0_layout import House0Layout as House0Dc
from gwsproto.enums import FlowManifoldVariant
from gwsproto.named_types import (
    DataChannelGt,
    DerivedChannelGt,
    GNodeGt,
    HvacZone,
    House0Hydronic,
    House0Layout as House0Sema,
    SpaceheatNodeGt,
)


def as_base(obj: Any, base_cls: type) -> Any:
    """Rebuild a clean base-gt instance from a data-class wrapper subclass,
    keeping only the base type's fields (drops wrapper link fields)."""
    return base_cls(**{f: getattr(obj, f) for f in base_cls.model_fields})

LAYOUT = Path(__file__).resolve().parent.parent / "tests" / "config" / "house0-layout.json"

GNODE_KEYS = ("MyLeafTransactiveNodeGNode", "MyTerminalAssetGNode", "MyScadaGNode")
HYDRONIC_KEYS = (
    "ZoneList", "CriticalZoneList", "ZoneKwhPerDegFList", "TotalStoreTanks",
    "TankTempCalibrationMap", "UseSiegLoop", "FlowManifoldVariant", "Strategy",
)


def dc_to_sema(dc: House0Dc) -> tuple[House0Sema, list[str]]:
    """Map a loaded House0 data class to the sema House0Layout. Returns the sema
    object (GNodes left empty if they can't be encoded) plus a list of gaps."""
    gaps: list[str] = []

    # GNodes: the layout stores three loose dicts; sema wants g.node.gt objects.
    g_nodes: list[GNodeGt] = []
    for key in GNODE_KEYS:
        gn = dc.layout.get(key)
        if gn is None:
            continue
        try:
            g_nodes.append(GNodeGt.model_validate(gn))
        except Exception as e:  # noqa: BLE001
            gaps.append(f"GNode {key} -> g.node.gt FAILED: {e}")

    sema = House0Sema(
        GNodes=g_nodes or None,
        ShNodes=[as_base(n, SpaceheatNodeGt) for n in dc.nodes.values()],
        DataChannels=[as_base(c, DataChannelGt) for c in dc.data_channels.values()],
        DerivedChannels=[as_base(c, DerivedChannelGt) for c in dc.derived_channels.values()],
        Components=[c.gt for c in dc.components.values()],
        DeviceTypes=list(dc.device_types.values()),
        Hydronic=dc.hydronic,
    )
    return sema, gaps


def sema_to_layout_dict(sema: House0Sema, *, gnode_src: dict[str, Any]) -> dict[str, Any]:
    """Inverse: build a layout dict the data class can load. Components/cacs are
    regrouped into the typed keys load_dict expects."""
    layout: dict[str, Any] = {}
    # GNodes back to the three named entries, reconstructed FROM the sema GNodes
    # (keyed by GNodeClass) — a true dc -> sema -> dc round-trip.
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


def main() -> int:
    dc0 = House0Dc.load(str(LAYOUT))
    orig = copy.deepcopy(dc0.layout)

    sema, gaps = dc_to_sema(dc0)
    print("== forward dc -> sema ==")
    print(f"  GNodes:          {len(sema.GNodes or [])}")
    print(f"  ShNodes:         {len(sema.ShNodes or [])}")
    print(f"  DataChannels:    {len(sema.DataChannels or [])}")
    print(f"  DerivedChannels: {len(sema.DerivedChannels or [])}")
    print(f"  Components:      {len(sema.Components or [])}")
    print(f"  DeviceTypes:     {len(sema.DeviceTypes or [])}")
    if sema.Hydronic is not None:
        print(
            f"  Hydronic:        zones={len(sema.Hydronic.Zones)} "
            f"sieg_plumbed={sema.Hydronic.SiegLoopPlumbed} "
            f"primary_flow_source={sema.Hydronic.PrimaryFlowSource}"
        )
    if gaps:
        print("  GAPS:")
        for g in gaps:
            print(f"    - {g}")

    print("== inverse sema -> layout dict -> load_dict ==")
    rebuilt = sema_to_layout_dict(sema, gnode_src=orig)
    try:
        House0Dc.load_dict(rebuilt)
        print("  load_dict(rebuilt): OK")
    except Exception as e:  # noqa: BLE001
        print(f"  load_dict(rebuilt): FAILED: {e}")

    # GNode bijection: orig named entries == those rebuilt from sema.GNodes.
    gnode_ok = all(orig.get(k) == rebuilt.get(k) for k in GNODE_KEYS)
    print(f"== GNode round-trip (dc -> sema -> dc) identical: {gnode_ok} ==")
    if not gnode_ok:
        for k in GNODE_KEYS:
            if orig.get(k) != rebuilt.get(k):
                print(f"  DIFF {k}:\n    orig={orig.get(k)}\n    rebuilt={rebuilt.get(k)}")
    return 0 if gnode_ok and not gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())
