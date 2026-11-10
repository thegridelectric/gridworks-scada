"""The plant link: what a simulated layout's sensors and relays reach the
plant through. The broker form is exercised broker-less through its payload
seam and a recording client; the in-process form is the seam a test plays
the plant on."""

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from gwproactor.config import MQTTClient
from gwsproto.enums import ChangeRelayPin

from clock import ManualClock
from plant import PlantReadings
from plant_link import (
    PLANT_SILENT_AFTER_S,
    BrokerPlantLink,
    InProcessPlantLink,
    PlantLinkKind,
    build_plant_link,
    plant_flux_topic,
)
from scada_app import ScadaApp
from tests.named_types.sema_oracle import codec

CONFIG = Path(__file__).parent / "config"
SCADA_ALIAS = "d1.isone.ct.keene.hazel.scada"
PLANT_ALIAS = "d1.isone.ct.keene.hazel.ta"
READ_MS = 1_735_689_600_123
ENERGIZE = ChangeRelayPin.Energize
DE_ENERGIZE = ChangeRelayPin.DeEnergize


class Monotonic:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


class RecordingClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict, int]] = []
        self.subscribed: list[str] = []

    def publish(self, topic: str, payload: bytes, qos: int) -> None:
        self.published.append((topic, json.loads(payload), qos))

    def subscribe(self, topic: str) -> None:
        self.subscribed.append(topic)


def in_process(monotonic: Monotonic | None = None) -> InProcessPlantLink:
    return InProcessPlantLink(
        silent_after_s=PLANT_SILENT_AFTER_S, monotonic=monotonic or Monotonic()
    )


def broker_link(monotonic: Monotonic | None = None) -> tuple[BrokerPlantLink, RecordingClient]:
    link = BrokerPlantLink(
        config=MQTTClient(),
        scada_alias=SCADA_ALIAS,
        plant_alias=PLANT_ALIAS,
        clock=ManualClock(start_s=1_700_000_000),
        silent_after_s=PLANT_SILENT_AFTER_S,
        monotonic=monotonic or Monotonic(),
    )
    client = RecordingClient()
    link.client = client  # type: ignore[assignment]
    return link, client


def flux_payload(values: dict[str, int], **overrides: Any) -> bytes:
    flux = {
        "ChannelNameList": list(values),
        "ValueList": list(values.values()),
        "ScadaReadTimeUnixMs": READ_MS,
        "ActualTimeUtc": "2026-06-12T13:20:00.000Z",
        "TypeName": "sim.plant.flux",
        "Version": "000",
    } | overrides
    return json.dumps(
        {
            "Header": {
                "Src": PLANT_ALIAS,
                "Dst": SCADA_ALIAS,
                "MessageType": flux["TypeName"],
                "MessageId": "7499defd-c54a-4061-a37a-17f3c84f88a2",
                "AckRequired": False,
                "TypeName": "gridworks.header",
                "Version": "001",
            },
            "Payload": flux,
            "TypeName": "gw",
        }
    ).encode()


def test_each_sensor_gets_its_own_channels_in_flux_order() -> None:
    link = in_process()
    tank: list[PlantReadings] = []
    flow: list[PlantReadings] = []
    link.sense(["tank1-depth1", "tank1-depth2"], tank.append)
    link.sense(["dist-flow"], flow.append)

    link.show({"tank1-depth2": 48_200, "dist-flow": 410, "tank1-depth1": 51_000}, READ_MS)

    assert tank == [PlantReadings(("tank1-depth2", "tank1-depth1"), (48_200, 51_000), READ_MS)]
    assert flow == [PlantReadings(("dist-flow",), (410,), READ_MS)]


def test_a_sensor_hears_nothing_from_a_flux_without_its_channels() -> None:
    link = in_process()
    tank: list[PlantReadings] = []
    link.sense(["tank1-depth1"], tank.append)
    link.show({"dist-flow": 410}, READ_MS)
    assert tank == []
    assert link.unsensed_channels == {"dist-flow"}


def test_a_channel_has_one_sensor() -> None:
    link = in_process()
    link.sense(["dist-flow"], lambda _: None)
    with pytest.raises(ValueError, match="dist-flow already has a sensor"):
        link.sense(["dist-flow"], lambda _: None)


def test_a_relay_position_goes_to_the_plant_and_reads_back() -> None:
    link = in_process()
    assert link.relay("store-pump-relay") is None
    link.set_relay("store-pump-relay", ENERGIZE)
    assert link.relay("store-pump-relay") is ENERGIZE
    link.set_relay("store-pump-relay", DE_ENERGIZE)
    assert link.relay("store-pump-relay") is DE_ENERGIZE
    assert link.actuations == [
        ("store-pump-relay", ENERGIZE),
        ("store-pump-relay", DE_ENERGIZE),
    ]


def test_setting_an_unchanged_position_tells_the_plant_again() -> None:
    link = in_process()
    link.set_relay("store-pump-relay", ENERGIZE)
    link.set_relay("store-pump-relay", ENERGIZE)
    assert link.actuations == [("store-pump-relay", ENERGIZE)] * 2


def test_a_plant_first_heard_is_told_every_position_before_its_flux_lands() -> None:
    link = in_process()
    order: list[str] = []
    link.sense(["dist-flow"], lambda _: order.append(f"flux after {len(link.actuations)} actuations"))
    link.set_relay("store-pump-relay", ENERGIZE)
    link.set_relay("hp-scada-ops-relay", DE_ENERGIZE)
    link.actuations.clear()

    link.show({"dist-flow": 410}, READ_MS)

    assert link.actuations == [
        ("store-pump-relay", ENERGIZE),
        ("hp-scada-ops-relay", DE_ENERGIZE),
    ]
    assert order == ["flux after 2 actuations"]


def test_a_plant_heard_steadily_is_not_told_again() -> None:
    monotonic = Monotonic()
    link = in_process(monotonic)
    link.set_relay("store-pump-relay", ENERGIZE)
    link.show({"dist-flow": 410}, READ_MS)
    link.actuations.clear()

    monotonic.t += PLANT_SILENT_AFTER_S
    link.show({"dist-flow": 411}, READ_MS + 15_000)

    assert link.actuations == []


def test_a_plant_back_from_silence_is_told_every_position() -> None:
    monotonic = Monotonic()
    link = in_process(monotonic)
    link.set_relay("store-pump-relay", ENERGIZE)
    link.show({"dist-flow": 410}, READ_MS)
    link.actuations.clear()

    monotonic.t += PLANT_SILENT_AFTER_S + 0.1
    link.show({"dist-flow": 0}, READ_MS + 15_100)

    assert link.actuations == [("store-pump-relay", ENERGIZE)]


def test_flux_topic_is_the_wrapped_grammar_from_plant_to_scada() -> None:
    assert plant_flux_topic(PLANT_ALIAS, SCADA_ALIAS) == (
        "gw/d1-isone-ct-keene-hazel-ta/to/d1-isone-ct-keene-hazel-scada/sim-plant-flux"
    )


def test_broker_link_delivers_a_wrapped_flux() -> None:
    link, _ = broker_link()
    seen: list[PlantReadings] = []
    link.sense(["dist-flow", "dist-swt"], seen.append)
    link.take_payload(flux_payload({"dist-swt": 51_300, "dist-flow": 410}))
    assert seen == [PlantReadings(("dist-swt", "dist-flow"), (51_300, 410), READ_MS)]


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        json.dumps({"TypeName": "sim.plant.flux"}).encode(),
        flux_payload({"dist-flow": 410}, TypeName="synced.readings"),
        flux_payload({"dist-flow": 410}, ValueList=[410, 411]),
        flux_payload({"dist-flow": 410}, ValueList=[4.1]),
    ],
    ids=["not-json", "unwrapped", "another-word", "axiom-1", "non-integer-value"],
)
def test_broker_link_ignores_what_is_no_flux(payload: bytes) -> None:
    link, _ = broker_link()
    seen: list[PlantReadings] = []
    link.sense(["dist-flow"], seen.append)
    link.take_payload(payload)
    assert seen == []
    assert link.heard_at is None


@pytest.mark.parametrize("action", list(ChangeRelayPin))
def test_broker_link_sends_an_actuation_the_snapshot_decodes(action: ChangeRelayPin) -> None:
    link, client = broker_link()
    link.set_relay("store-pump-relay", action)

    [(topic, wire, qos)] = client.published
    assert topic == (
        "gw/d1-isone-ct-keene-hazel-scada/to/d1-isone-ct-keene-hazel-ta/sim-plant-actuation"
    )
    assert qos == 0
    assert wire["TypeName"] == "gw"
    assert wire["Header"]["Src"] == SCADA_ALIAS
    assert wire["Header"]["Dst"] == PLANT_ALIAS
    assert wire["Header"]["MessageType"] == "sim.plant.actuation"
    assert wire["Header"]["AckRequired"] is False
    actuation = codec().from_dict(wire["Payload"], auto_upgrade=False)
    assert actuation.to_dict() == wire["Payload"]
    assert wire["Payload"]["RelayName"] == "store-pump-relay"
    assert wire["Payload"]["Action"] == action.value
    assert wire["Payload"]["ActuationTimeUnixMs"] == 1_700_000_000_000


def test_broker_link_subscribes_and_restates_on_every_connect() -> None:
    link, client = broker_link()
    link.set_relay("store-pump-relay", ENERGIZE)
    client.published.clear()

    async def run() -> None:
        link.loop = asyncio.get_running_loop()
        for _ in range(2):
            paho_thread = threading.Thread(target=link.on_connect, args=(client,))
            paho_thread.start()
            paho_thread.join()
            await asyncio.sleep(0)

    asyncio.run(run())

    assert client.subscribed == [link.flux_topic] * 2
    assert [wire["Payload"]["RelayName"] for _, wire, _ in client.published] == [
        "store-pump-relay"
    ] * 2


def test_no_plant_link_without_a_simulated_device() -> None:
    link = build_plant_link(
        PlantLinkKind.Broker,
        False,
        mqtt_config=MQTTClient(),
        scada_alias=SCADA_ALIAS,
        plant_alias=PLANT_ALIAS,
        clock=ManualClock(start_s=1_700_000_000),
    )
    assert link is None


def app_settings(pair: str):
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / f"{pair}.layout.json"
    settings.paths.operational_params = CONFIG / f"{pair}.operational.params.json"
    settings.paths.mkdirs()
    return settings


@pytest.mark.parametrize("pair", ["gw.house0.no.sieg.hazel", "gw.nolan"])
def test_a_simulated_layout_reaches_its_plant_over_the_broker_by_default(pair: str) -> None:
    settings = app_settings(pair)
    assert settings.plant_link == PlantLinkKind.Broker
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    link = app.plant_link
    assert isinstance(link, BrokerPlantLink)
    assert app.scada.services.plant_link is link
    layout = app.hardware_layout
    assert link.flux_topic == plant_flux_topic(
        layout.terminal_asset_g_node_alias, layout.scada_g_node_alias
    )


def test_settings_pick_the_in_process_plant_link() -> None:
    settings = app_settings("gw.house0.no.sieg.hazel")
    settings.plant_link = PlantLinkKind.InProcess
    app = ScadaApp(app_settings=settings)
    assert isinstance(app.plant_link, InProcessPlantLink)
