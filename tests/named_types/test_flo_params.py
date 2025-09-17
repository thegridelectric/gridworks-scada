"""Tests flo.params type, version 001"""

from gwsproto.named_types import FloParams


def test_flo_params_generated() -> None:
    d = {
        "GNodeAlias": "d1.isone.ver.keene.holly",
        "FloParamsUid": "97eba574-bd20-45b5-bf82-9ba2f492d8f6",
        "HomeCity": "MILLINOCKET_ME",
        "TimezoneString": "US/Eastern",
        "StartUnixS": 1734539700,
        "TypeName": "flo.params",
        "Version": "001",
    }

    d2 = FloParams.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
