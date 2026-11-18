"""Tests gw1.scada.device.type.gt type, version 000"""


from gwsproto.data_classes.device_types.scada_krida import (
    krida_double_relay_board_16_device_type,
)
from gwsproto.named_types import ScadaDeviceTypeGt
from tests.named_types.sema_oracle import assert_refused


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

    assert_refused(ScadaDeviceTypeGt, d)


def test_gw1_scada_device_type_gt_axiom_5_energized_level_range() -> None:
    d = krida_double_relay_board_16_device_type.model_dump(
        by_alias=True, exclude_none=True
    )
    d["RelayEnergizedLevel"] = 2

    assert_refused(ScadaDeviceTypeGt, d, "Axiom 5")


def with_second_bus(name: str, number: int) -> dict:
    d = krida_double_relay_board_16_device_type.model_dump(
        by_alias=True, exclude_none=True
    )
    [first] = d["BusList"]
    d["BusList"] = [
        first,
        {"Name": name, "BusNumber": number, "TypeName": "i2c.bus", "Version": "000"},
    ]
    return d


def test_gw1_scada_device_type_gt_axiom_6_a_rejects_a_repeated_bus_name() -> None:
    [first] = krida_double_relay_board_16_device_type.BusList
    d = with_second_bus(first.Name, first.BusNumber + 1)

    assert_refused(ScadaDeviceTypeGt, d, "Axiom 6 \\(BusUniqueness\\) clause a")


def test_gw1_scada_device_type_gt_axiom_6_b_rejects_a_repeated_bus_number() -> None:
    [first] = krida_double_relay_board_16_device_type.BusList
    d = with_second_bus("SecondBus", first.BusNumber)

    assert_refused(ScadaDeviceTypeGt, d, "Axiom 6 \\(BusUniqueness\\) clause b")


def test_gw1_scada_device_type_gt_axiom_6_accepts_two_distinct_buses() -> None:
    [first] = krida_double_relay_board_16_device_type.BusList
    d = with_second_bus("SecondBus", first.BusNumber + 1)

    assert len(ScadaDeviceTypeGt.model_validate(d).BusList) == 2
