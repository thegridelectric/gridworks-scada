"""Tests go.dormant type, version 000"""

from gwsproto.named_types import GoDormant


def test_go_dormant_generated() -> None:
    d = {
        "ToName": "pico-cycler",
        "TypeName": "go.dormant",
        "Version": "001",
    }

    d2 = GoDormant.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
