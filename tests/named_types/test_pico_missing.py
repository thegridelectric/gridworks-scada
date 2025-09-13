"""Tests pico.missing type, version 000"""

from gwsproto.named_types import PicoMissing


def test_pico_missing_generated() -> None:
    d = {
        "ActorName": "dist-flow",
        "PicoHwUid": "pico-a12bdd",
        "TypeName": "pico.missing",
        "Version": "000",
    }

    d2 = PicoMissing.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
