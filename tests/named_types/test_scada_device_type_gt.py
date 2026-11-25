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


DAC_MUX = {
    "MuxName": "DacMux",
    "I2cBus": "DefaultBus",
    "I2cAddress": 112,
    "MuxType": "Tca9548a",
    "Channels": 8,
    "TypeName": "i2c.mux",
    "Version": "000",
}

CT_ADC = {
    "Name": "Ct",
    "I2cBus": "DefaultBus",
    "I2cAddress": 72,
    "AdcType": "Ads1115",
    "AdcReferenceVolts": 3.3,
    "Channels": 4,
    "MuxName": "DacMux",
    "MuxChannel": 4,
    "TypeName": "i2c.ct.interface.capability",
    "Version": "000",
}


def krida_with_ct_adc(**ct_overrides: object) -> dict:
    d = krida_double_relay_board_16_device_type.model_dump(
        by_alias=True, exclude_none=True
    )
    d["Muxes"] = [DAC_MUX]
    d["CtAdc"] = {**CT_ADC, **ct_overrides}
    return d


def test_gw1_scada_device_type_gt_axiom_4_accepts_ct_adc_behind_mux() -> None:
    d = krida_with_ct_adc()

    d2 = ScadaDeviceTypeGt.model_validate(d).model_dump(
        by_alias=True, exclude_none=True
    )

    assert d2 == d


def test_gw1_scada_device_type_gt_axiom_4_a_rejects_ct_adc_mux_not_in_muxes() -> None:
    d = krida_with_ct_adc(MuxName="GhostMux")

    assert_refused(ScadaDeviceTypeGt, d, match="Axiom 4 \\(MuxConsistency\\) failed")


def test_gw1_scada_device_type_gt_axiom_4_b_rejects_ct_adc_mux_channel_out_of_bounds() -> (
    None
):
    d = krida_with_ct_adc(MuxChannel=9)

    assert_refused(ScadaDeviceTypeGt, d, match="Axiom 4 \\(MuxConsistency\\) failed")


def test_gw1_scada_device_type_gt_axiom_4_c_rejects_ct_adc_bus_unlike_mux_bus() -> None:
    d = krida_with_ct_adc(I2cBus="SecondBus")
    d["BusList"].append(
        {"Name": "SecondBus", "BusNumber": 2, "TypeName": "i2c.bus", "Version": "000"}
    )

    assert_refused(ScadaDeviceTypeGt, d, match="Axiom 4 \\(MuxConsistency\\) failed")
