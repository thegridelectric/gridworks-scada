"""Tests ally.gives.up type, version 001"""

from gwsproto.named_types import AllyGivesUp


def test_ally_gives_up_generated() -> None:
    d = {
        "Reason": "ScadaBlind",
        "Cause": "buffer-depth1 stale",
        "TypeName": "ally.gives.up",
        "Version": "001",
    }

    d2 = AllyGivesUp.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
