"""Tests remaining.elec type, version 000"""

from gwsproto.named_types import RemainingElec


def test_remaining_elec_generated() -> None:
    d = {
        "FromGNodeAlias":"hw1.isone.me.versant.keene.beech.scada",
        "RemainingWattHours": 4420,
        "MessageId": "f5627079-bef3-45f7-b247-5a6ae19b2b5b",
        "TypeName": "remaining.elec",
        "Version": "000",
    }

    d2 = RemainingElec.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
