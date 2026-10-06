"""Rejecting tests for gw.boiler.backup/000 and gw.element.backup/000."""

import pytest
from pydantic import ValidationError

from gwsproto.named_types import BoilerBackup, ElementBackup


def test_gw_boiler_backup_validates() -> None:
    b = BoilerBackup(
        FailsafeRelayName="hp-failsafe-relay",
        AquastatCtrlRelayName="aquastat-ctrl-relay",
        InService=True,
    )
    assert b.InService


def test_gw_boiler_backup_axiom_1() -> None:
    """One relay cannot hold both roles."""
    with pytest.raises(ValidationError, match=r"Axiom 1 \(DistinctRelays\)"):
        BoilerBackup(
            FailsafeRelayName="hp-failsafe-relay",
            AquastatCtrlRelayName="hp-failsafe-relay",
            InService=True,
        )


def test_gw_element_backup_axiom_1() -> None:
    with pytest.raises(ValidationError, match=r"Axiom 1 \(NonEmptyElements\)"):
        ElementBackup(ElementRelayNames=[], InService=False)


def test_gw_element_backup_axiom_2() -> None:
    with pytest.raises(ValidationError, match=r"Axiom 2 \(DistinctElements\)"):
        ElementBackup(
            ElementRelayNames=["buffer-top-elt-relay", "buffer-top-elt-relay"],
            InService=False,
        )
