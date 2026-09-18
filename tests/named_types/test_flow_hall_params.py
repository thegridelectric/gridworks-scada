"""Tests flow.hall.params type, version 200"""

from gwsproto.enums import PicoBoardVariant
from gwsproto.named_types import FlowHallParams

WIRE_200 = {
    "HwUid": "pico_1a2b3c",
    "ActorNodeName": "dist-flow",
    "FlowNodeName": "dist-flow",
    "PublishTicklistPeriodS": 10,
    "PublishEmptyTicklistAfterS": 60,
    "PicoBoardVariant": "PicoRaspberryWifi2040",
    "MicropythonVersion": "1.24.1",
    "TypeName": "flow.hall.params",
    "Version": "200",
}


def test_flow_hall_params_generated() -> None:
    d2 = FlowHallParams.model_validate(WIRE_200).model_dump(exclude_none=True)

    assert d2 == WIRE_200


def test_unknown_board_coerces_to_unknown() -> None:
    d = dict(WIRE_200, PicoBoardVariant="Esp32Something")
    assert (
        FlowHallParams.model_validate(d).PicoBoardVariant == PicoBoardVariant.Unknown
    )
