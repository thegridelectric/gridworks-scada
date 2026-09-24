"""The sim pico flow word decodes its own shape and rejects a malformed HwUid."""

import pytest

from gwsproto.named_types import SimPicoFlowModuleComponentGt


def component() -> dict:
    return {
        "ComponentId": "3702ecf7-32a5-4582-a073-13b8edc1154f",
        "DeviceType": "GridworksPicoFlowHall",
        "SerialNumber": "NA",
        "HwUid": "pico_60e352",
        "FlowNodeName": "dist-flow",
        "FlowMeterType": "SaierFlowSensor",
        "HzCalcMethod": "BasicExpWeightedAvg",
        "GpmFromHzMethod": "Constant",
        "ConstantGallonsPerTick": 0.0009,
        "SendHz": True,
        "SendGallons": False,
        "SendTickLists": False,
        "NoFlowMs": 250,
        "AsyncCaptureThresholdGpmTimes100": 5,
        "SimLifeS": 30,
        "SimulatesTypeName": "pico.flow.module.component.gt",
        "SimulatesVersion": "001",
        "TypeName": "sim.pico.flow.module.component.gt",
        "Version": "000",
    }


def test_sim_pico_flow_module_component_gt_round_trip() -> None:
    d = component()
    word = SimPicoFlowModuleComponentGt.model_validate(d)
    assert word.model_dump(by_alias=True, exclude_none=True) == d


def test_sim_pico_flow_module_component_gt_axiom_1_bad_hw_uid() -> None:
    d = component()
    d["HwUid"] = "pico_60E352"
    with pytest.raises(ValueError, match="HwUid"):
        SimPicoFlowModuleComponentGt.model_validate(d)
