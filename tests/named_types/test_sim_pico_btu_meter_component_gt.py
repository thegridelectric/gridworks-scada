"""The sim pico BTU meter word decodes its own shape and holds the CT pairing."""


from gwsproto.named_types import SimPicoBtuMeterComponentGt
from tests.named_types.sema_oracle import assert_conforms, assert_refused


def component() -> dict:
    return {
        "ComponentId": "7fc24a16-37e6-442b-83cb-9b5be5a3cce9",
        "DeviceType": "Gw101",
        "SerialNumber": "example",
        "FlowChannelName": "scada",
        "HotChannelName": "scada",
        "ColdChannelName": "scada",
        "ReadCtVoltage": True,
        "SendHz": False,
        "FlowMeterType": "MakeModel",
        "HzCalcMethod": "BasicExpWeightedAvg",
        "TempCalcMethod": "SimpleBeta",
        "GpmFromHzMethod": "Constant",
        "ThermistorBeta": 0,
        "GallonsPerPulse": 1,
        "AsyncCaptureDeltaGpmX100": 0,
        "AsyncCaptureDeltaCelsiusX100": 0,
        "SimulatesTypeName": "pico.btu.meter.component.gt",
        "SimulatesVersion": "000",
        "TypeName": "sim.pico.btu.meter.component.gt",
        "Version": "000",
        "CtChannelName": "hp-ct-volts",
        "AsyncCaptureDeltaCtVoltsX100": 50,
    }


def test_sim_pico_btu_meter_component_gt_round_trip() -> None:
    d = component()
    word = SimPicoBtuMeterComponentGt.model_validate(d)
    assert word.model_dump(by_alias=True, exclude_none=True) == d
    assert_conforms(word)


def test_sim_pico_btu_meter_component_gt_axiom_1_ct_read_without_delta() -> None:
    d = component()
    del d["AsyncCaptureDeltaCtVoltsX100"]
    assert_refused(SimPicoBtuMeterComponentGt, d, match="Axiom 1")


def test_sim_pico_btu_meter_component_gt_axiom_1_delta_without_ct_read() -> None:
    d = component()
    d["ReadCtVoltage"] = False
    del d["CtChannelName"]
    assert_refused(SimPicoBtuMeterComponentGt, d, match="Axiom 1")


def test_sim_pico_btu_meter_component_gt_axiom_2_ct_read_without_channel() -> None:
    d = component()
    del d["CtChannelName"]
    assert_refused(SimPicoBtuMeterComponentGt, d, match="Axiom 2")
