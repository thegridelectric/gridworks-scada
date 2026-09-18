"""The zone-call-circuit channel axiom bodies the layout words share."""

from typing import Any, Iterable


def check_circuit_whitewire_channel_resolution(
    circuits: Iterable[Any],
    data_channels: Iterable[Any],
    label: str,
) -> None:
    """Every circuit's WhitewireChannelName is the Name of a DataChannel."""
    data_names = {c.Name for c in data_channels}
    for circuit in circuits:
        if circuit.WhitewireChannelName not in data_names:
            raise ValueError(
                f"{label} failed: circuit {circuit.CircuitPosition} names "
                f"WhitewireChannelName {circuit.WhitewireChannelName!r}, which "
                "is not a channel in DataChannels."
            )


def check_circuit_heat_call_channel(
    circuits: Iterable[Any],
    derived_channels: Iterable[Any],
    label: str,
) -> None:
    """Each circuit has exactly one DerivedChannel with Strategy "heat-call"
    whose InputChannelNames is [the circuit's WhitewireChannelName]."""
    heat_calls = [c for c in derived_channels if c.Strategy == "heat-call"]
    for circuit in circuits:
        matches = [
            c.Name
            for c in heat_calls
            if list(c.InputChannelNames) == [circuit.WhitewireChannelName]
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{label} failed: circuit {circuit.CircuitPosition} needs exactly one "
                f"heat-call DerivedChannel with InputChannelNames "
                f"[{circuit.WhitewireChannelName!r}], found {matches}."
            )
