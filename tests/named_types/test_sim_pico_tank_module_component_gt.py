"""The sim pico tank module word decodes its own shape and holds its sensor order to a permutation."""

import pytest

from gwsproto.named_types import SimPicoTankModuleComponentGt


def component() -> dict:
    return {
        "ComponentId": "4058e925-2399-4908-91a1-5c4c63cf89f0",
        "DeviceType": "GridworksTankModule3",
        "TempCalcMethod": "SimpleBeta",
        "ThermistorBeta": 1,
        "SendMicroVolts": False,
        "Samples": 1,
        "NumSampleAverages": 1,
        "SerialNumber": "example",
        "AsyncCaptureDeltaMicroVolts": 0,
        "SimulatesTypeName": "pico.tank.module.component.gt",
        "SimulatesVersion": "012",
        "TypeName": "sim.pico.tank.module.component.gt",
        "Version": "001",
        "PicoHwUid": "pico_a1b2c3",
        "SensorOrder": [3, 1, 2],
    }


def test_sim_pico_tank_module_component_gt_round_trip() -> None:
    d = component()
    word = SimPicoTankModuleComponentGt.model_validate(d)
    assert word.model_dump(by_alias=True, exclude_none=True) == d


def test_sim_pico_tank_module_component_gt_axiom_3_repeated_sensor() -> None:
    d = component()
    d["SensorOrder"] = [1, 1, 2]
    with pytest.raises(ValueError, match="SensorOrder"):
        SimPicoTankModuleComponentGt.model_validate(d)
