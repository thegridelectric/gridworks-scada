"""The circulator axiom shared by the layout words: every circulator in
Hydronic.Circulators has its running channel on the circulator-running
strategy, reading the input it declares. One implementation here; each
type's check_axiom_<n> supplies its own label."""

from typing import Iterable

from gwsproto.enums import Quantity, TelemetryName, Unit
from gwsproto.named_types.circulator import Circulator
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.names.core.node_names import CoreNodeNames


def check_circulator_running_channels(
    derived_channels: Iterable[DerivedChannelGt],
    data_channels: Iterable[DataChannelGt],
    circulators: Iterable[Circulator],
    axiom: str,
) -> None:
    """a. Exactly one DerivedChannel named RunningChannelName, on the
    circulator-running strategy from derived-generator with Unitless output.
    b. It reads [PowerChannelName] when present, else [CtChannelName], and the
    input is a DataChannel, PowerW when it is the power channel."""
    derived = list(derived_channels)
    data_by_name = {c.Name: c for c in data_channels}
    for circ in circulators:
        matches = [d for d in derived if d.Name == circ.RunningChannelName]
        if len(matches) != 1:
            raise ValueError(
                f"{axiom} a. failed: circulator {circ.PumpNodeName!r} needs exactly one "
                f"DerivedChannel named {circ.RunningChannelName!r}, found {len(matches)}."
            )
        d = matches[0]
        if (
            d.Strategy != "circulator-running"
            or d.CreatedByNodeName != CoreNodeNames.derived_generator
            or d.OutputUnit != Unit.Unitless
            or d.OutputQuantity != Quantity.Unitless
        ):
            raise ValueError(
                f"{axiom} a. failed: {d.Name!r} SHALL have Strategy circulator-running, "
                "CreatedByNodeName derived-generator and Unitless output; got Strategy "
                f"{d.Strategy!r}, CreatedByNodeName {d.CreatedByNodeName!r}, OutputUnit "
                f"{d.OutputUnit}, OutputQuantity {d.OutputQuantity}."
            )
        is_power = circ.PowerChannelName is not None
        expected = circ.PowerChannelName if is_power else circ.CtChannelName
        if list(d.InputChannelNames) != [expected]:
            raise ValueError(
                f"{axiom} b. failed: {d.Name!r} SHALL read [{expected!r}], got "
                f"{list(d.InputChannelNames)}."
            )
        inp = data_by_name.get(expected)
        if inp is None:
            raise ValueError(
                f"{axiom} b. failed: input {expected!r} of {d.Name!r} is not the Name of "
                "a DataChannel."
            )
        if is_power and inp.TelemetryName != TelemetryName.PowerW:
            raise ValueError(
                f"{axiom} b. failed: PowerChannelName {expected!r} SHALL have TelemetryName "
                f"PowerW, got {inp.TelemetryName}."
            )
