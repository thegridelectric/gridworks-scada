"""The pico tank module word decodes its own shape and holds its sensor order to a permutation."""


from gwsproto.named_types import PicoTankModuleComponentGt
from tests.named_types.sema_oracle import assert_conforms, assert_refused


def component() -> dict:
    return {
        "ComponentId": "b58df331-f649-4563-9e40-d3e500529679",
        "DeviceType": "GridworksTankModule3",
        "TempCalcMethod": "SimpleBeta",
        "ThermistorBeta": 1,
        "SendMicroVolts": False,
        "Samples": 1,
        "NumSampleAverages": 1,
        "SerialNumber": "example",
        "PicoBoardVariant": "PicoRaspberryWifi2040",
        "TypeName": "pico.tank.module.component.gt",
        "Version": "012",
        "PicoHwUid": "pico_a1b2c3",
        "SensorOrder": [3, 1, 2],
    }


def test_pico_tank_module_component_gt_round_trip() -> None:
    d = component()
    word = PicoTankModuleComponentGt.model_validate(d)
    assert word.model_dump(by_alias=True, exclude_none=True) == d
    assert_conforms(word)


def test_pico_tank_module_component_gt_axiom_3_repeated_sensor() -> None:
    d = component()
    d["SensorOrder"] = [1, 1, 2]
    assert_refused(PicoTankModuleComponentGt, d, match="SensorOrder")
