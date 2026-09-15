"""derived-generator flow arithmetic on the sim House0 fixture: the `sum` and
`difference` strategies that tie a Siegenthaler loop's three flows together
(primary-flow = sieg-send-flow + sieg-flow). A house that measures primary
(beech) derives sieg-send-flow by difference; one that derives primary (maple)
sums. Covers the handler math, the fire-on-either-input rule, and the
registration contract (one shared unit; difference takes exactly two inputs).
These are the first tests either strategy has."""

import uuid
from pathlib import Path

import pytest

from actors.derived_generator import DerivedGenerator
from actors.sim_sensor import SimSensorActor
from gwproto.message import Message
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import EmissionMethod, Quantity, Unit
from gwsproto.named_types import SingleReading
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
}
# which sieg flow each little house derives, and from what
DERIVED_SIEG_FLOW = {
    "house0-orange": ("sieg-send-flow", lambda v: v["primary-flow"] - v["sieg-flow"]),
    "house0-willow": ("primary-flow", lambda v: v["sieg-send-flow"] + v["sieg-flow"]),
}


def make_app(layout: str, ops: str) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


@pytest.fixture
def app() -> ScadaApp:
    return make_app(*PAIRS["house0-orange"])


@pytest.fixture
def actor(app: ScadaApp) -> DerivedGenerator:
    generator = app.get_communicator_as_type(H0N.derived_generator, DerivedGenerator)
    assert generator is not None
    return generator


def flow_channel(
    actor: DerivedGenerator, name: str, strategy: str, inputs: list[str]
) -> DerivedChannel:
    """A hand-built GpmX100 derived flow channel owned by this generator."""
    any_derived = next(iter(actor.layout.derived_channels.values()))
    return DerivedChannel(
        Id=str(uuid.uuid4()),
        Name=name,
        CreatedByNodeName=actor.name,
        Strategy=strategy,
        InputChannelNames=inputs,
        OutputUnit=Unit.GpmX100,
        OutputQuantity=Quantity.FlowRate,
        EmissionMethod=EmissionMethod.OnTrigger,
        DisplayName=name,
        TerminalAssetAlias=any_derived.TerminalAssetAlias,
        created_by_node=any_derived.created_by_node,
    )


def capture_sends(actor: DerivedGenerator) -> list:
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def reading(name: str, value: int) -> SingleReading:
    return SingleReading(
        ChannelName=name, Value=value, ScadaReadTimeUnixMs=1_700_000_000_000
    )


def register(actor: DerivedGenerator, dc: DerivedChannel) -> None:
    actor.layout.derived_channels[dc.Name] = dc
    actor.init_derived_channels()


def test_difference_emits_minuend_minus_subtrahend(actor: DerivedGenerator) -> None:
    dc = flow_channel(
        actor, "sieg-send-flow", "difference", ["primary-flow", "sieg-flow"]
    )
    sent = capture_sends(actor)
    actor.data.latest_channel_values["sieg-flow"] = 300
    actor.handle_difference(dc, reading("primary-flow", 1000))
    assert len(sent) == 1
    _, out = sent[0]
    assert out.ChannelName == "sieg-send-flow"
    assert out.Value == 700


def test_difference_waits_for_both_inputs(actor: DerivedGenerator) -> None:
    dc = flow_channel(
        actor, "sieg-send-flow", "difference", ["primary-flow", "sieg-flow"]
    )
    sent = capture_sends(actor)
    actor.data.latest_channel_values.pop("sieg-flow", None)
    actor.handle_difference(dc, reading("primary-flow", 1000))
    assert sent == []  # sieg-flow never seen: nothing emitted


def test_difference_fires_on_either_input(actor: DerivedGenerator) -> None:
    dc = flow_channel(
        actor, "sieg-send-flow", "difference", ["primary-flow", "sieg-flow"]
    )
    sent = capture_sends(actor)
    actor.data.latest_channel_values["primary-flow"] = 1000
    actor.handle_difference(
        dc, reading("sieg-flow", 250)
    )  # the subtrahend arrives fresh
    assert sent[0][1].Value == 750


def test_sum_emits_total_of_inputs(actor: DerivedGenerator) -> None:
    dc = flow_channel(
        actor, "primary-flow-derived", "sum", ["sieg-send-flow", "sieg-flow"]
    )
    sent = capture_sends(actor)
    actor.data.latest_channel_values["sieg-flow"] = 300
    actor.handle_sum(dc, reading("sieg-send-flow", 700))
    assert sent[0][1].Value == 1000


def test_difference_registration_requires_exactly_two_inputs(
    actor: DerivedGenerator,
) -> None:
    dc = flow_channel(
        actor, "bad-diff", "difference", ["primary-flow", "sieg-flow", "store-flow"]
    )
    with pytest.raises(RuntimeError, match="exactly two"):
        register(actor, dc)


def test_difference_registration_requires_one_shared_unit(
    actor: DerivedGenerator,
) -> None:
    # buffer-depth1-device is a water temperature; primary-flow is GpmTimes100
    assert actor.layout.channel_registry.unit("buffer-depth1-device") is not None
    dc = flow_channel(
        actor, "bad-diff", "difference", ["primary-flow", "buffer-depth1-device"]
    )
    with pytest.raises(RuntimeError, match="share one unit"):
        register(actor, dc)


def test_difference_registers_under_both_inputs(actor: DerivedGenerator) -> None:
    dc = flow_channel(
        actor, "sieg-send-flow", "difference", ["primary-flow", "sieg-flow"]
    )
    register(actor, dc)
    assert dc in actor.derived_by_input["primary-flow"]
    assert dc in actor.derived_by_input["sieg-flow"]


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_each_house_derives_its_missing_sieg_flow_from_its_sim_sensors(pair: str) -> None:
    """End to end on both simulated House0 fixtures: every sim flow sensor
    posts its standing readings the way it does on its timer (to the scada,
    then to the derived generator, whose handlers read the other addend from
    the scada's latest values), and the derived generator emits exactly the
    one sieg flow the house does not measure — orange's sieg-send-flow by
    difference, willow's primary-flow by sum — with the value the sim
    readings imply."""
    app = make_app(*PAIRS[pair])
    scada = app.scada
    generator = app.get_communicator_as_type(H0N.derived_generator, DerivedGenerator)
    assert generator is not None
    emitted: list[SingleReading] = []
    generator._send_to = lambda dst, payload, src=None: emitted.append(payload)

    def route(sensor: SimSensorActor):
        def deliver(dst, payload, src=None):
            message = Message(Src=sensor.name, Dst=dst.name, Payload=payload)
            if dst.name == scada.name:
                scada.process_internal_message(message)
            elif dst.name == generator.name:
                generator.process_message(message)
            else:
                raise AssertionError(f"{sensor.name} posted to {dst.name}")

        return deliver

    sensors = [
        c for c in (app.get_communicator(n) for n in app.get_communicator_names())
        if isinstance(c, SimSensorActor)
    ]
    flow_sensors = [
        s for s in sensors if any(n.endswith("-flow") for n in s.readings().ChannelNameList)
    ]
    assert len(flow_sensors) == 4, [s.name for s in flow_sensors]
    for sensor in flow_sensors:
        sensor._send_to = route(sensor)
        sensor.post()

    derived_name, arithmetic = DERIVED_SIEG_FLOW[pair]
    latest = scada.data.latest_channel_values
    assert latest["sieg-flow"] > 0  # the sim sensors post real flow, not idle zeros
    assert [r.ChannelName for r in emitted if r.ChannelName.endswith("-flow")] == [derived_name]
    (reading,) = [r for r in emitted if r.ChannelName == derived_name]
    assert reading.Value == arithmetic(latest)
    assert derived_name not in app.hardware_layout.data_channels  # derived, never measured
