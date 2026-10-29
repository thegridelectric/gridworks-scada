"""Rejecting tests for gw.circulator/000: the pump's running input."""

import pytest
from pydantic import ValidationError

from gwsproto.enums import CirculatorRole
from gwsproto.named_types import Circulator


def test_gw_circulator_validates() -> None:
    c = Circulator(
        PumpNodeName="dist-pump",
        Role=CirculatorRole.Dist,
        RunningChannelName="dist-pump-running",
        FlowChannelName="dist-flow",
        PowerChannelName="dist-pump-pwr",
        ZeroTenNodeName="dist-010v",
    )
    assert c.Role == CirculatorRole.Dist
    assert c.CtChannelName is None


def test_gw_circulator_ct_only_input() -> None:
    c = Circulator(
        PumpNodeName="secondary-pump",
        Role=CirculatorRole.Secondary,
        RunningChannelName="secondary-pump-running",
        CtChannelName="secondary-pump-ct",
    )
    assert c.PowerChannelName is None


def test_gw_circulator_axiom_1() -> None:
    """A circulator with neither a power nor a CT channel has no running input."""
    with pytest.raises(ValidationError, match=r"Axiom 1 \(InputDeclared\)"):
        Circulator(
            PumpNodeName="dist-pump",
            Role=CirculatorRole.Dist,
            RunningChannelName="dist-pump-running",
        )


def test_gw_circulator_unknown_role_decodes_to_default() -> None:
    c = Circulator.model_validate(
        {
            "PumpNodeName": "dist-pump",
            "Role": "Buffer",
            "RunningChannelName": "dist-pump-running",
            "PowerChannelName": "dist-pump-pwr",
            "TypeName": "gw.circulator",
            "Version": "000",
        }
    )
    assert c.Role == CirculatorRole.Unknown
