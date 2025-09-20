"""Tests ally.gives.up type, version 000"""

from gwsproto.named_types import AllyGivesUp


def test_ally_gives_up_generated() -> None:
    d = {
        "Reason": "Missing forecasts required for operation",
        "TypeName": "ally.gives.up",
        "Version": "000",
    }

    d2 = AllyGivesUp.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
