"""Tests wake.up type, version 000"""

from gwsproto.named_types import WakeUp


def test_wake_up_generated() -> None:
    d = {
        "ToName": "pico-cycler",
        "TypeName": "wake.up",
        "Version": "000",
    }

    d2 = WakeUp.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
