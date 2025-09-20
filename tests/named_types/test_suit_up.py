"""Tests suit.up type, version 000"""

from gwsproto.named_types import SuitUp


def test_suit_up_generated() -> None:
    d = {
        "ToNode": "aa",
        "FromNode": "s",
        "TypeName": "suit.up",
        "Version": "000",
    }

    d2 = SuitUp.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
