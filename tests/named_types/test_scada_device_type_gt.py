"""Tests gw1.scada.device.type.gt type, version 000"""

import pytest
from pydantic import ValidationError

from gwsproto.data_classes.device_types.scada_krida import (
    krida_double_relay_board_16_device_type,
)
from gwsproto.named_types import ScadaDeviceTypeGt


def test_scada_device_type_gt_generated() -> None:
    # The gw108 record's authoring source lives in tlayouts (vendored sema
    # instance); scada exercises its decode through the layout fixtures.
    for record in (krida_double_relay_board_16_device_type,):
        d = record.model_dump(by_alias=True, exclude_none=True)

        d2 = ScadaDeviceTypeGt.model_validate(d).model_dump(
            by_alias=True, exclude_none=True
        )

        assert d2 == d


def test_scada_device_type_gt_supports_pin_readback_required() -> None:
    d = krida_double_relay_board_16_device_type.model_dump(
        by_alias=True, exclude_none=True
    )
    del d["SupportsPinReadback"]

    with pytest.raises(ValidationError):
        ScadaDeviceTypeGt.model_validate(d)
