"""Tests send.layout type, version 000"""

from gwsproto.named_types import SendLayout


def test_send_layout_generated() -> None:
    d = {
        "FromGNodeAlias": "d1.isone.ct.orange",
        "FromName": "a",
        "ToName": "s",
        "TypeName": "send.layout",
        "Version": "000",
    }

    d2 = SendLayout.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
