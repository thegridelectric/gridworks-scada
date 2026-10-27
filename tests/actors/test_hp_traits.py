"""The HP_TRAITS rows against each unit's measured power signature: a
standby sample reads as stopped, the first running sample as running."""

import pytest

from actors.hp_boss.sensing import HP_TRAITS
from gwsproto.enums import DeviceType


@pytest.mark.parametrize(
    "device_type, standby_w, first_running_w",
    [
        # elm, 2026-10-26, eGauge hp-odu-pwr: standby 0 to 66 W (crankcase
        # heater on), first running sample 1131 W, steady state 4.2 to 5.8 kW
        (DeviceType.ArcticMAHRW030ZA, 66, 1131),
    ],
)
def test_measured_signature_crosses_the_lines(
    device_type: DeviceType, standby_w: int, first_running_w: int
) -> None:
    row = HP_TRAITS[device_type]
    assert standby_w < row.off_below_w
    assert first_running_w > row.on_above_w
