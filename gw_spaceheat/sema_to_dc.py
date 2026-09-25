"""sema_to_dc — load the dc layout the scada runs from its authored artifacts.

The gen machinery lives in tlayouts (the authoring home, on the sema snapshot);
scada consumes its two authored artifacts per home:

    gw.house0.layout.json ⊕ gw.operational.params.json
        ──load_layout──▶ HydronicLayout

The layout word decodes to its typed sema word and is handed straight to
`HydronicLayout.from_sema` — the runtime layout holds the word, so there is no
dict round-trip. `assemble_runtime_layout` validates the two assembly checks
against the raw artifacts before decode: assembly coverage (the ops file covers
every channel the static layout declares) and the poll floor (PollPeriodMs ≥
the device type's MinPollPeriodMs; the layout owns the floor, the ops file owns
PollPeriodMs). Capture tuning stays on the ops artifact's CaptureTuningList and
is threaded through (typed) to HydronicLayout.capture_tuning_by_channel.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.enums import GNodeClass, SiegLoopStrategy
from gwsproto.named_types import (
    House0FamilyParams,
    House0Layout,
    NolanFamilyParams,
    NolanLayout,
    OperationalParams,
)
from gwsproto.property_format import LeftRightDotStr

# The authored static artifact names its sema layout type; dispatch on it.
SEMA_LAYOUT_BY_TYPENAME: dict[LeftRightDotStr, type[House0Layout] | type[NolanLayout]] = {
    word.type_name_value(): word for word in (House0Layout, NolanLayout)
}

# The ONLY layout ⊕ family-params pairings a scada may boot. The operational
# params carry a FamilyParams block whose TypeName names the layout family; a
# crossed pair would tune one family's plant with the other family's knobs.
# The pairing is checked at load and a mismatch refuses the boot outright.
# Keys and values are TypeNames (left.right.dot vocabulary), validated at load.
APPROVED_PAIRS: dict[LeftRightDotStr, LeftRightDotStr] = TypeAdapter(
    dict[LeftRightDotStr, LeftRightDotStr]
).validate_python(
    {
        House0Layout.type_name_value(): House0FamilyParams.type_name_value(),
        NolanLayout.type_name_value(): NolanFamilyParams.type_name_value(),
    }
)


def check_approved_pair(layout_type_name: str, family_type_name: str) -> None:
    """Refuse any layout ⊕ family-params pairing outside APPROVED_PAIRS.
    Raises ValueError naming both words and the one partner that is allowed."""
    expected = APPROVED_PAIRS.get(layout_type_name)
    if expected is None:
        raise ValueError(
            f"Layout word {layout_type_name!r} has no approved family-params "
            f"partner. Approved pairs: {APPROVED_PAIRS}."
        )
    if family_type_name != expected:
        raise ValueError(
            f"Mismatched artifact pair: layout {layout_type_name!r} SHALL be paired "
            f"with {expected!r}, got family params {family_type_name!r}. "
            f"Approved pairs: {APPROVED_PAIRS}. Scada will not start."
        )


def check_scada_alias(
    word: House0Layout | NolanLayout, ops_word: OperationalParams
) -> None:
    """The ops word names the Scada it tunes; refuse a pair whose ScadaAlias is
    not the alias of the layout's Scada GNode."""
    layout_aliases = [
        g.Alias for g in word.GNodes if g.GNodeClass == GNodeClass.Scada.value
    ]
    if layout_aliases != [ops_word.ScadaAlias]:
        raise ValueError(
            f"Mismatched artifact pair: operational params ScadaAlias "
            f"{ops_word.ScadaAlias!r} is not the layout's Scada GNode alias "
            f"{layout_aliases}. Scada will not start."
        )


def zero_ten_power_on_volts_times_ten(ops: OperationalParams, node_name: str) -> int:
    """The power-on level of the 0-10V output driven by `node_name`, in volts
    times ten. Raises when the ops word
    names no level for the node: a DAC-backed output boots only with one."""
    for entry in ops.ZeroTenPowerOnList:
        if entry.NodeName == node_name:
            return entry.PowerOnVoltsTimesTen
    raise ValueError(
        f"{ops.TypeName} carries no zero.ten.power.on entry for {node_name}"
    )


def check_sieg_loop_strategy(ops_word: OperationalParams) -> None:
    """The loader refuses a strategy the scada cannot run yet. Raises on
    LwtControl, which is not built."""
    family = ops_word.FamilyParams
    if (
        isinstance(family, House0FamilyParams)
        and family.SiegLoopStrategy is SiegLoopStrategy.LwtControl
    ):
        raise ValueError(
            f"{family.TypeName} names SiegLoopStrategy LwtControl, which the scada "
            "cannot run."
        )


def decode_operational_params(ops: dict[str, Any]) -> OperationalParams:
    """Decode the operational-params artifact."""
    type_name = ops.get("TypeName")
    if type_name != OperationalParams.type_name_value():
        raise ValueError(
            f"Operational params TypeName {type_name!r} is not "
            f"{OperationalParams.type_name_value()!r}."
        )
    return OperationalParams.model_validate(ops)


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
) -> HydronicLayout:
    """Load the dc HydronicLayout from the two authored artifacts. The pair
    SHALL be approved (see APPROVED_PAIRS); a mismatch raises. The layout word
    is handed to HydronicLayout.from_sema directly — no dict round-trip — and
    the capture tuning is taken (typed) from the operational-params word."""
    static = json.loads(Path(static_path).read_text())
    ops = json.loads(Path(ops_path).read_text())
    check_approved_pair(
        str(static.get("TypeName")),
        str((ops.get("FamilyParams") or {}).get("TypeName")),
    )
    # Validates assembly coverage + poll floor against the raw artifacts; raises.
    assemble_runtime_layout(static, ops)
    word = SEMA_LAYOUT_BY_TYPENAME[str(static["TypeName"])].model_validate(static)
    ops_word = decode_operational_params(ops)
    check_scada_alias(word, ops_word)
    check_sieg_loop_strategy(ops_word)
    return HydronicLayout.from_sema(
        word, capture_tuning=ops_word.CaptureTuningList, **load_kwargs
    )


def load_layout(
    layout_path: Path | str,
    ops_path: Path | str,
    **load_kwargs: Any,
) -> HydronicLayout:
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

