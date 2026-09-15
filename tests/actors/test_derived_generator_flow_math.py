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
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import EmissionMethod, Quantity, Unit
from gwsproto.named_types import SingleReading
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.house0.sim.layout.json"
    settings.paths.operational_params = CONFIG / "gw.house0.sim.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


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
