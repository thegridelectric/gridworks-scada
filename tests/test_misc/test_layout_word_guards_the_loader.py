"""A broken layout is refused by the layout word's axioms on the load path,
before any data class is built. Each test breaks one thing in a copy of a
fixture layout and loads it through ops_and_sema_to_dc."""

import json
from pathlib import Path
from typing import Callable

import pytest

from sema_to_dc import ops_and_sema_to_dc

CONFIG = Path(__file__).parent.parent / "config"
# (layout, ops, number of DerivedChannelInputsAcyclic in that layout word);
# DataChannelNodeResolution is the axiom before it and
# DerivedChannelCreatorResolution the one before that.
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json", 18),
    "house0-willow": (
        "gw.house0.willow.layout.json",
        "gw.house0.willow.operational.params.json",
        22,
    ),
}


def load_broken(tmp_path: Path, layout: str, ops: str, mutate: Callable[[dict], None]) -> None:
    d = json.loads((CONFIG / layout).read_text())
    mutate(d)
    path = tmp_path / layout
    path.write_text(json.dumps(d))
    ops_and_sema_to_dc(path, CONFIG / ops)


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_a_derived_input_naming_no_channel_is_refused_by_the_word(
    tmp_path: Path, pair: str
) -> None:
    layout, ops, axiom = PAIRS[pair]

    def mutate(d: dict) -> None:
        identity = next(c for c in d["DerivedChannels"] if c["Strategy"] == "identity")
        identity["InputChannelNames"] = ["no-such-channel"]

    with pytest.raises(ValueError, match=rf"Axiom {axiom} \(.*failed \(a\)"):
        load_broken(tmp_path, layout, ops, mutate)


@pytest.mark.parametrize("pair", sorted(PAIRS))
@pytest.mark.parametrize(
    ("field", "clause"), [("AboutNodeName", "a"), ("CapturedByNodeName", "b")]
)
def test_a_data_channel_naming_no_node_is_refused_by_the_word(
    tmp_path: Path, pair: str, field: str, clause: str
) -> None:
    layout, ops, inputs_axiom = PAIRS[pair]

    def mutate(d: dict) -> None:
        d["DataChannels"][-1][field] = "no-such-node"

    with pytest.raises(ValueError, match=rf"Axiom {inputs_axiom - 1} \(.*failed \({clause}\)"):
        load_broken(tmp_path, layout, ops, mutate)


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_a_derived_channel_naming_no_creating_node_is_refused_by_the_word(
    tmp_path: Path, pair: str
) -> None:
    layout, ops, inputs_axiom = PAIRS[pair]

    def mutate(d: dict) -> None:
        identity = next(c for c in d["DerivedChannels"] if c["Strategy"] == "identity")
        identity["CreatedByNodeName"] = "no-such-node"

    with pytest.raises(ValueError, match=rf"Axiom {inputs_axiom - 2} \(.*failed \(a\)"):
        load_broken(tmp_path, layout, ops, mutate)


# --- the backup pair check ---------------------------------------------------

BACKUP_PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
}


def load_pair(
    tmp_path: Path,
    layout: str,
    ops: str,
    mutate_layout: Callable[[dict], None],
    mutate_ops: Callable[[dict], None],
) -> None:
    """Load a copy of the fixture pair with each side changed."""
    layout_d = json.loads((CONFIG / layout).read_text())
    mutate_layout(layout_d)
    layout_path = tmp_path / layout
    layout_path.write_text(json.dumps(layout_d))
    ops_d = json.loads((CONFIG / ops).read_text())
    mutate_ops(ops_d)
    ops_path = tmp_path / ops
    ops_path.write_text(json.dumps(ops_d))
    ops_and_sema_to_dc(layout_path, ops_path)


def uses_backup(value: bool) -> Callable[[dict], None]:
    def mutate(ops: dict) -> None:
        ops["UsesBackupWhenCold"] = value

    return mutate


def no_backup(layout: dict) -> None:
    del layout["Hydronic"]["Backup"]
    layout["ShNodes"] = [n for n in layout["ShNodes"] if n["Name"] != "backup"]


def backup_out_of_service(layout: dict) -> None:
    layout["Hydronic"]["Backup"]["InService"] = False


@pytest.mark.parametrize("pair", sorted(BACKUP_PAIRS))
def test_using_backup_when_cold_needs_a_backup_in_the_layout(tmp_path: Path, pair: str) -> None:
    """The pair is checked before any actor is built: UsesBackupWhenCold true
    with no Backup does not boot, whichever family."""
    layout, ops = BACKUP_PAIRS[pair]
    with pytest.raises(ValueError, match="UsesBackupWhenCold"):
        load_pair(tmp_path, layout, ops, no_backup, uses_backup(True))


@pytest.mark.parametrize("pair", sorted(BACKUP_PAIRS))
def test_using_backup_when_cold_needs_the_backup_in_service(tmp_path: Path, pair: str) -> None:
    layout, ops = BACKUP_PAIRS[pair]
    with pytest.raises(ValueError, match="InService"):
        load_pair(tmp_path, layout, ops, backup_out_of_service, uses_backup(True))


@pytest.mark.parametrize("pair", sorted(BACKUP_PAIRS))
def test_not_using_backup_when_cold_needs_no_backup(tmp_path: Path, pair: str) -> None:
    """A layout with no backup, or one out of service, boots with
    UsesBackupWhenCold false; the backup is simply never used."""
    layout, ops = BACKUP_PAIRS[pair]
    load_pair(tmp_path, layout, ops, no_backup, uses_backup(False))
    load_pair(tmp_path, layout, ops, backup_out_of_service, uses_backup(False))


def test_a_nolan_house_using_backup_when_cold_needs_an_element_backup(tmp_path: Path) -> None:
    """A Nolan machine has no boiler branch: a boiler backup with
    UsesBackupWhenCold true does not boot."""
    layout, ops = BACKUP_PAIRS["nolan"]

    def boiler_backup(d: dict) -> None:
        d["Hydronic"]["Backup"] = {
            "TypeName": "gw.boiler.backup",
            "Version": "000",
            "FailsafeRelayName": "zone1-bedrooms-failsafe-relay",
            "AquastatCtrlRelayName": "zone1-bedrooms-ops-relay",
            "InService": True,
        }

    with pytest.raises(ValueError, match="element backup"):
        load_pair(tmp_path, layout, ops, boiler_backup, uses_backup(True))
