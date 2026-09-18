"""A pico's params post carries its board and MicroPython version; the actor
holds them against the layout's component and warns once per difference."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from gwproto import Message

from actors.api_btu_meter import ApiBtuMeter
from actors.api_flow_module import ApiFlowModule
from actors.api_tank_module import ApiTankModule
from actors.pico_identity import PicoIdentity
from gwsproto.enums import LogLevel, PicoBoardVariant
from gwsproto.named_types import AsyncBtuParams, FlowHallParams, Glitch, TankModuleParams
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
}
LAYOUT_BOARD = PicoBoardVariant.PicoRaspberryWifi2040
OTHER_BOARD = PicoBoardVariant.PicoWiznetEth2350


def test_matching_post_shows_no_difference() -> None:
    identity = PicoIdentity(LAYOUT_BOARD, "1.24.1")
    assert identity.differences(LAYOUT_BOARD, "1.24.1") == []


def test_each_differing_field_is_its_own_difference() -> None:
    identity = PicoIdentity(LAYOUT_BOARD, "1.24.1")
    found = identity.differences(OTHER_BOARD, "1.25.0")
    assert [(d.field, d.layout_value, d.posted_value) for d in found] == [
        ("PicoBoardVariant", LAYOUT_BOARD.value, OTHER_BOARD.value),
        ("MicropythonVersion", "1.24.1", "1.25.0"),
    ]


def test_a_layout_with_no_micropython_version_holds_the_post_to_none() -> None:
    identity = PicoIdentity(LAYOUT_BOARD, None)
    assert identity.differences(LAYOUT_BOARD, "1.25.0") == []


def test_a_standing_difference_shows_once_and_a_new_value_shows_again() -> None:
    identity = PicoIdentity(LAYOUT_BOARD, None)
    assert len(identity.differences(OTHER_BOARD, "1.24.1")) == 1
    assert identity.differences(OTHER_BOARD, "1.24.1") == []
    assert len(identity.differences(PicoBoardVariant.Unknown, "1.24.1")) == 1


def with_real_pico(pair: tuple[str, str], node_name: str, hw_uid_field: str) -> dict:
    """The pair's sim layout with `node_name`'s sim pico component restated
    as the word it simulates, on LAYOUT_BOARD."""
    layout = json.loads((CONFIG / pair[0]).read_text())
    node = next(n for n in layout["ShNodes"] if n["Name"] == node_name)
    component = next(
        c for c in layout["Components"] if c["ComponentId"] == node["ComponentId"]
    )
    component["TypeName"] = component.pop("SimulatesTypeName")
    component["Version"] = component.pop("SimulatesVersion")
    component.pop("SimLifeS", None)
    component.pop("SimRebootS", None)
    component[hw_uid_field] = "pico_1a2b3c"
    component["PicoBoardVariant"] = LAYOUT_BOARD.value
    return layout


def boot(tmp_path: Path, pair: tuple[str, str], layout: dict) -> ScadaApp:
    layout_path = tmp_path / pair[0]
    layout_path.write_text(json.dumps(layout))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout_path
    settings.paths.operational_params = CONFIG / pair[1]
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def capture_sends(actor: Any) -> list:
    actor.sent = []
    actor._send_to = lambda dst, payload, src=None: actor.sent.append(payload)
    return actor.sent


def warnings(sent: list) -> list[Glitch]:
    return [p for p in sent if isinstance(p, Glitch) and p.Type == LogLevel.Warning]


def tank_params(board: PicoBoardVariant) -> TankModuleParams:
    return TankModuleParams(
        HwUid="pico_1a2b3c",
        ActorNodeName="tank1",
        PicoAB="a",
        CapturePeriodS=60,
        Samples=1000,
        NumSampleAverages=10,
        AsyncCaptureDeltaMicroVolts=2000,
        PicoBoardVariant=board,
        MicropythonVersion="1.24.1",
    )


@pytest.mark.parametrize("pair_name", sorted(PAIRS))
def test_tank_module_warns_once_on_a_board_the_layout_does_not_say(
    tmp_path: Path, pair_name: str
) -> None:
    pair = PAIRS[pair_name]
    app = boot(tmp_path, pair, with_real_pico(pair, "tank1", "PicoHwUid"))
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    sent = capture_sends(actor)

    actor.process_message(
        Message(Src="tank1", Dst="tank1", Payload=tank_params(LAYOUT_BOARD))
    )
    assert warnings(sent) == []

    for _ in range(2):
        actor.process_message(
            Message(Src="tank1", Dst="tank1", Payload=tank_params(OTHER_BOARD))
        )
    [glitch] = warnings(sent)
    assert "PicoBoardVariant" in glitch.Summary
    assert OTHER_BOARD.value in glitch.Details
    assert LAYOUT_BOARD.value in glitch.Details


@pytest.mark.parametrize("pair_name", sorted(PAIRS))
def test_a_sim_pico_tank_holds_no_identity(tmp_path: Path, pair_name: str) -> None:
    pair = PAIRS[pair_name]
    app = boot(tmp_path, pair, json.loads((CONFIG / pair[0]).read_text()))
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    sent = capture_sends(actor)

    actor.process_message(
        Message(Src="tank1", Dst="tank1", Payload=tank_params(OTHER_BOARD))
    )
    assert warnings(sent) == []


def btu_params(actor: ApiBtuMeter, board: PicoBoardVariant) -> AsyncBtuParams:
    gt = actor._component.gt
    return AsyncBtuParams(
        HwUid="pico_1a2b3c",
        ActorNodeName=actor.name,
        FlowChannelName=gt.FlowChannelName,
        SendHz=gt.SendHz,
        ReadCtVoltage=gt.ReadCtVoltage,
        HotChannelName=gt.HotChannelName,
        ColdChannelName=gt.ColdChannelName,
        CtChannelName=gt.CtChannelName,
        ThermistorBeta=gt.ThermistorBeta,
        CapturePeriodS=60,
        GallonsPerPulse=gt.GallonsPerPulse,
        AsyncCaptureDeltaCelsiusX100=gt.AsyncCaptureDeltaCelsiusX100,
        AsyncCaptureDeltaGpmX100=gt.AsyncCaptureDeltaGpmX100,
        AsyncCaptureDeltaCtVoltsX100=gt.AsyncCaptureDeltaCtVoltsX100,
        PicoBoardVariant=board,
        MicropythonVersion="1.24.1",
    )


def test_btu_meter_warns_once_on_a_board_the_layout_does_not_say(tmp_path: Path) -> None:
    pair = PAIRS["nolan"]
    app = boot(tmp_path, pair, with_real_pico(pair, "primary-btu", "HwUid"))
    actor = app.get_communicator_as_type("primary-btu", ApiBtuMeter)
    assert actor is not None
    sent = capture_sends(actor)

    actor.process_message(
        Message(Src=actor.name, Dst=actor.name, Payload=btu_params(actor, LAYOUT_BOARD))
    )
    assert warnings(sent) == []

    for _ in range(2):
        actor.process_message(
            Message(Src=actor.name, Dst=actor.name, Payload=btu_params(actor, OTHER_BOARD))
        )
    [glitch] = warnings(sent)
    assert "PicoBoardVariant" in glitch.Summary


HOUSE0_PAIRS = ["orange", "willow"]


def with_hall_flow_pico(pair: tuple[str, str]) -> dict:
    """The pair's sim layout with dist-flow read by a hall-effect flow pico
    on LAYOUT_BOARD, as a House0 deployment has it."""
    layout = json.loads((CONFIG / pair[0]).read_text())
    node = next(n for n in layout["ShNodes"] if n["Name"] == "dist-flow")
    node["ActorClass"] = "ApiFlowModule"
    layout["Components"] = [
        c for c in layout["Components"] if c["ComponentId"] != node["ComponentId"]
    ] + [
        {
            "TypeName": "pico.flow.module.component.gt",
            "Version": "001",
            "ComponentId": node["ComponentId"],
            "DeviceType": "GridworksPicoFlowHall",
            "DisplayName": "Dist Flow HallFlowModule",
            "HwUid": "pico_1a2b3c",
            "Enabled": True,
            "SerialNumber": "1025",
            "FlowNodeName": "dist-flow",
            "FlowMeterType": "SaierFlowSensor",
            "HzCalcMethod": "BasicExpWeightedAvg",
            "GpmFromHzMethod": "Constant",
            "ConstantGallonsPerTick": 0.0009,
            "SendHz": True,
            "SendGallons": False,
            "SendTickLists": False,
            "NoFlowMs": 250,
            "AsyncCaptureThresholdGpmTimes100": 20,
            "PublishEmptyTicklistAfterS": 7,
            "PublishTicklistPeriodS": 10,
            "ExpAlpha": 0.2,
            "PicoBoardVariant": LAYOUT_BOARD.value,
        }
    ]
    return layout


def flow_params(board: PicoBoardVariant) -> FlowHallParams:
    return FlowHallParams(
        HwUid="pico_1a2b3c",
        ActorNodeName="dist-flow",
        FlowNodeName="dist-flow",
        PublishTicklistPeriodS=10,
        PublishEmptyTicklistAfterS=7,
        PicoBoardVariant=board,
        MicropythonVersion="1.24.1",
    )


@pytest.mark.parametrize("pair_name", HOUSE0_PAIRS)
def test_flow_module_warns_once_on_a_board_the_layout_does_not_say(
    tmp_path: Path, pair_name: str
) -> None:
    pair = PAIRS[pair_name]
    app = boot(tmp_path, pair, with_hall_flow_pico(pair))
    actor = app.get_communicator_as_type("dist-flow", ApiFlowModule)
    assert actor is not None
    sent = capture_sends(actor)

    actor.process_message(
        Message(Src="dist-flow", Dst="dist-flow", Payload=flow_params(LAYOUT_BOARD))
    )
    assert warnings(sent) == []

    for _ in range(2):
        actor.process_message(
            Message(Src="dist-flow", Dst="dist-flow", Payload=flow_params(OTHER_BOARD))
        )
    [glitch] = warnings(sent)
    assert "PicoBoardVariant" in glitch.Summary


class Post:
    """A pico's HTTP post, as far as a params handler reads it."""

    def __init__(self, body: dict) -> None:
        self.body = body

    async def text(self) -> str:
        return json.dumps(self.body)


def capture_threadsafe(actor: Any) -> list[Message]:
    queued: list[Message] = []
    actor.services.send_threadsafe = queued.append
    return queued


@pytest.mark.parametrize("pair_name", HOUSE0_PAIRS)
def test_flow_module_answers_a_200_post_in_200_and_queues_it_for_the_identity_check(
    tmp_path: Path, pair_name: str
) -> None:
    pair = PAIRS[pair_name]
    app = boot(tmp_path, pair, with_hall_flow_pico(pair))
    actor = app.get_communicator_as_type("dist-flow", ApiFlowModule)
    assert actor is not None
    queued = capture_threadsafe(actor)
    posted = flow_params(OTHER_BOARD)

    response = asyncio.run(
        actor._handle_hall_params_post(Post(posted.model_dump(mode="json")))
    )

    answer = FlowHallParams.model_validate_json(response.text)
    assert answer.PicoBoardVariant == OTHER_BOARD
    assert [m.Payload for m in queued] == [posted]


@pytest.mark.parametrize("pair_name", HOUSE0_PAIRS)
def test_flow_module_answers_a_101_post_in_101_with_no_identity_check(
    tmp_path: Path, pair_name: str
) -> None:
    pair = PAIRS[pair_name]
    app = boot(tmp_path, pair, with_hall_flow_pico(pair))
    actor = app.get_communicator_as_type("dist-flow", ApiFlowModule)
    assert actor is not None
    queued = capture_threadsafe(actor)

    response = asyncio.run(
        actor._handle_hall_params_post(
            Post(
                {
                    "HwUid": "pico_1a2b3c",
                    "ActorNodeName": "dist-flow",
                    "FlowNodeName": "dist-flow",
                    "PublishTicklistPeriodS": 5,
                    "PublishEmptyTicklistAfterS": 5,
                    "TypeName": "flow.hall.params",
                    "Version": "101",
                }
            )
        )
    )

    answer = json.loads(response.text)
    assert answer["Version"] == "101"
    assert answer["PublishTicklistPeriodS"] == 10
    assert "PicoBoardVariant" not in answer
    assert queued == []


@pytest.mark.parametrize("pair_name", sorted(PAIRS))
def test_tank_module_queues_a_params_post_for_the_identity_check(
    tmp_path: Path, pair_name: str
) -> None:
    pair = PAIRS[pair_name]
    app = boot(tmp_path, pair, with_real_pico(pair, "tank1", "PicoHwUid"))
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    queued = capture_threadsafe(actor)
    posted = tank_params(OTHER_BOARD)

    response = asyncio.run(actor._handle_params_post(Post(posted.model_dump(mode="json"))))

    assert TankModuleParams.model_validate_json(response.text).PicoBoardVariant == OTHER_BOARD
    assert [m.Payload for m in queued] == [posted]


def test_btu_meter_queues_a_params_post_for_the_identity_check(tmp_path: Path) -> None:
    pair = PAIRS["nolan"]
    app = boot(tmp_path, pair, with_real_pico(pair, "primary-btu", "HwUid"))
    actor = app.get_communicator_as_type("primary-btu", ApiBtuMeter)
    assert actor is not None
    queued = capture_threadsafe(actor)
    posted = btu_params(actor, OTHER_BOARD)

    asyncio.run(actor._handle_async_btu_params_post(Post(posted.model_dump(mode="json"))))

    assert [m.Payload.PicoBoardVariant for m in queued] == [OTHER_BOARD]
