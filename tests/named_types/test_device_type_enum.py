"""DeviceType is the closed vocabulary, enforced at construction.

Every twin carrying a device category types it as AnyDeviceType — the union of
the real (gw1.device.type) and simulated (gw1.sim.device.type) enums — so a
name outside both fails where the instance is built, not later at bind time.
The wire form stays the same PascalCase string.
"""

import pytest
from pydantic import ValidationError

from gwsproto.enums import DeviceType, SimDeviceType
from gwsproto.named_types import (
    ElectricMeterDeviceTypeGt,
    I2cBus,
    ScadaBoardComponentGt,
    ScadaDeviceTypeGt,
)

COMPONENT_ID = "00000000-0000-4000-8000-000000000001"


def scada_device_type(device_type: str) -> ScadaDeviceTypeGt:
    return ScadaDeviceTypeGt(
        DeviceType=device_type,
        BusList=[I2cBus(Name="DefaultBus", BusNumber=1)],
        TelemetryNameList=[],
        NativeGpioInputs=[],
        NativeGpioOutputs=[],
        Expanders=[],
        Muxes=[],
        I2cRelays=[],
        ThermistorAdcs=[],
        Dacs=[],
        SupportsPinReadback=True,
        RelayEnergizedLevel=0,
    )


def electric_meter_device_type(device_type: str) -> ElectricMeterDeviceTypeGt:
    return ElectricMeterDeviceTypeGt(
        DeviceType=device_type,
        TelemetryNameList=[],
    )


def test_unknown_value_decodes_to_the_default_on_the_enum() -> None:
    """Each enum alone decodes an unknown name to its sema default; the
    refusal of a stale name belongs to the AnyDeviceType field."""
    assert DeviceType("Gw108RevC") is DeviceType.EgaugePowerMeter
    assert SimDeviceType("SimGw109") is SimDeviceType.SimSensor


def test_field_refuses_a_name_outside_both_vocabularies() -> None:
    with pytest.raises(ValidationError, match="not a gw1.device.type"):
        ScadaBoardComponentGt(ComponentId=COMPONENT_ID, DeviceType="Gw108RevC")
    with pytest.raises(ValidationError, match="not a gw1.device.type"):
        ScadaBoardComponentGt(ComponentId=COMPONENT_ID, DeviceType="SimGw109")


@pytest.mark.parametrize("device_type", ["Gw108RevB", "SimGw108"])
def test_component_twin_round_trips(device_type: str) -> None:
    component = ScadaBoardComponentGt(ComponentId=COMPONENT_ID, DeviceType=device_type)
    assert component.model_dump(by_alias=True)["DeviceType"] == device_type
    assert f'"DeviceType":"{device_type}"' in component.model_dump_json()


def test_component_twin_rejects_stale_name() -> None:
    with pytest.raises(ValidationError):
        ScadaBoardComponentGt(ComponentId=COMPONENT_ID, DeviceType="Gw108RevC")


@pytest.mark.parametrize("device_type", ["Gw108RevB", "SimGw108"])
def test_scada_device_type_record_round_trips(device_type: str) -> None:
    record = scada_device_type(device_type)
    assert record.model_dump(by_alias=True)["DeviceType"] == device_type
    assert f'"DeviceType":"{device_type}"' in record.model_dump_json()


def test_scada_device_type_record_rejects_stale_name() -> None:
    with pytest.raises(ValidationError):
        scada_device_type("Gw108RevC")


def test_electric_meter_device_type_record_round_trips() -> None:
    record = electric_meter_device_type("EgaugePowerMeter")
    assert record.model_dump(by_alias=True)["DeviceType"] == "EgaugePowerMeter"
    assert '"DeviceType":"EgaugePowerMeter"' in record.model_dump_json()


def test_electric_meter_device_type_record_rejects_stale_name() -> None:
    with pytest.raises(ValidationError):
        electric_meter_device_type("EgaugePowerMeter4030")
