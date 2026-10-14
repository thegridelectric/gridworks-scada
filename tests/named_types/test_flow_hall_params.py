"""Tests flow.hall.params type, version 101"""

from gwsproto.named_types import FlowHallParams

WIRE_101 = {
    "HwUid": "pico_1a2b3c",
    "ActorNodeName": "dist-flow",
    "FlowNodeName": "dist-flow",
    "PublishTicklistPeriodS": 10,
    "PublishEmptyTicklistAfterS": 60,
    "TypeName": "flow.hall.params",
    "Version": "101",
}


def test_flow_hall_params_generated() -> None:
    d2 = FlowHallParams.model_validate(WIRE_101).model_dump(exclude_none=True)

    assert d2 == WIRE_101
