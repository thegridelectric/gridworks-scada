"""A tank pico's params post is answered with the micro-volt threshold the
scada translates from the depths' authored temperature delta."""

import asyncio
import json
from pathlib import Path

from actors.api_tank_module import (
    CAPTURE_DELTA_MATCH_C,
    ApiTankModule,
    micro_volt_capture_delta,
    microvolts_at_c,
)
from gwproto import Message
from gwsproto.enums import LogLevel, PicoBoardVariant
from gwsproto.named_types import Glitch, TankModuleParams
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIR = ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json")
TANK_MODULE_BETA = 3977


class Post:
    """A pico's HTTP post, as far as a params handler reads it."""

    def __init__(self, body: dict) -> None:
        self.body = body

    async def text(self) -> str:
        return json.dumps(self.body)


def test_translation_is_the_divider_drop_at_the_match_temperature() -> None:
    delta = micro_volt_capture_delta(14, TANK_MODULE_BETA)
    assert delta == microvolts_at_c(CAPTURE_DELTA_MATCH_C, TANK_MODULE_BETA) - microvolts_at_c(
        CAPTURE_DELTA_MATCH_C + 0.14, TANK_MODULE_BETA
    )
    assert 3500 < delta < 4500  # 0.14 C at 130 F on the 5.65 kOhm divider


def test_sim_tank_module_answers_a_params_post_with_the_translated_delta(tmp_path: Path) -> None:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / PAIR[0]
    settings.paths.operational_params = CONFIG / PAIR[1]
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    actor.services.send_threadsafe = lambda message: None  # the identity check is not under test
    authored = {
        actor.layout.capture_tuning_by_channel[f"tank1-depth{depth}-device"].AsyncCaptureDelta
        for depth in (1, 2, 3)
    }
    assert authored == {14}
    expected = micro_volt_capture_delta(14, actor._component.gt.ThermistorBeta)

    posted = TankModuleParams(
        HwUid=actor._component.gt.PicoHwUid,
        ActorNodeName="tank1",
        PicoAB="a",
        CapturePeriodS=60,
        Samples=1000,
        NumSampleAverages=10,
        AsyncCaptureDeltaMicroVolts=500,  # the firmware default a fresh pico boots on
        PicoBoardVariant=PicoBoardVariant.PicoRaspberryWifi2040,
        MicropythonVersion="1.24.1",
    )
    response = asyncio.run(actor._handle_params_post(Post(posted.model_dump(mode="json"))))
    answered = TankModuleParams.model_validate_json(response.text)
    assert answered.AsyncCaptureDeltaMicroVolts == expected


def test_a_post_that_differs_from_the_answer_sends_an_info_glitch() -> None:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / PAIR[0]
    settings.paths.operational_params = CONFIG / PAIR[1]
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    actor = app.get_communicator_as_type("tank1", ApiTankModule)
    assert actor is not None
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append(payload)
    answered = actor.answered_params()

    def post(**changes: int) -> None:
        actor.process_message(
            Message(
                Src="tank1",
                Dst="tank1",
                Payload=TankModuleParams(
                    HwUid=actor._component.gt.PicoHwUid,
                    ActorNodeName="tank1",
                    PicoAB="a",
                    PicoBoardVariant=PicoBoardVariant.PicoRaspberryWifi2040,
                    MicropythonVersion="1.24.1",
                    **{**answered, **changes},
                ),
            )
        )

    post()
    assert sent == []
    post(AsyncCaptureDeltaMicroVolts=500, CapturePeriodS=answered["CapturePeriodS"] + 1)
    infos = [p for p in sent if isinstance(p, Glitch) and p.Type == LogLevel.Info]
    assert len(infos) == 1
    assert "AsyncCaptureDeltaMicroVolts" in infos[0].Summary
    assert "CapturePeriodS" in infos[0].Summary
    assert f"AsyncCaptureDeltaMicroVolts 500/{answered['AsyncCaptureDeltaMicroVolts']}" in infos[0].Details
