"""The zone-call-circuit channel axiom bodies the layout words share."""

from typing import Any, Iterable

from gwsproto.enums import ZoneSetpointSource


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


def check_circuit_temp_channel_resolution(
    circuits: Iterable[Any],
    data_channels: Iterable[Any],
    derived_channels: Iterable[Any],
    label: str,
) -> None:
    """Every circuit's TempChannelName is the Name of a DataChannel or a
    DerivedChannel, and that channel carries temperature."""
    quantity_by_name = {c.Name: str(c.Quantity) for c in data_channels}
    quantity_by_name.update({c.Name: str(c.OutputQuantity) for c in derived_channels})
    for circuit in circuits:
        name = circuit.TempChannelName
        if name is None:
            continue
        if name not in quantity_by_name:
            raise ValueError(
                f"{label} failed: circuit {circuit.Name!r} names TempChannelName "
                f"{name!r}, which is not a channel in DataChannels or DerivedChannels."
            )
        if quantity_by_name[name] != "Temperature":
            raise ValueError(
                f"{label} failed: circuit {circuit.Name!r} names {name!r}, whose "
                f"quantity is {quantity_by_name[name]}, not Temperature."
            )


def check_circuit_setpoint_channel(
    circuits: Iterable[Any],
    data_channels: Iterable[Any],
    derived_channels: Iterable[Any],
    label: str,
) -> None:
    """Every circuit's SetpointChannelName is the Name of a DataChannel or a
    DerivedChannel carrying temperature. A Learned circuit's is a
    DerivedChannel with Strategy "simple-falling-edge-setpoint" whose
    InputChannelNames contain the circuit's TempChannelName and its heat-call
    channel."""
    derived_by_name = {d.Name: d for d in derived_channels}
    quantity_by_name = {c.Name: str(c.Quantity) for c in data_channels}
    quantity_by_name.update(
        {name: str(d.OutputQuantity) for name, d in derived_by_name.items()}
    )
    for circuit in circuits:
        name = circuit.SetpointChannelName
        if name is None:
            continue
        if name not in quantity_by_name:
            raise ValueError(
                f"{label} failed: circuit {circuit.Name!r} names SetpointChannelName "
                f"{name!r}, which is not a channel in DataChannels or DerivedChannels."
            )
        if quantity_by_name[name] != "Temperature":
            raise ValueError(
                f"{label} failed: circuit {circuit.Name!r} names {name!r}, whose "
                f"quantity is {quantity_by_name[name]}, not Temperature."
            )
        if circuit.SetpointSource != ZoneSetpointSource.Learned:
            continue
        if name not in derived_by_name:
            raise ValueError(
                f"{label} failed: circuit {circuit.Name!r} has SetpointSource "
                f"Learned, so {name!r} SHALL be a channel in DerivedChannels."
            )
        inputs = list(derived_by_name[name].InputChannelNames)
        heat_calls = [
            d.Name
            for d in derived_by_name.values()
            if d.Strategy == "heat-call"
            and list(d.InputChannelNames) == [circuit.WhitewireChannelName]
        ]
        missing = [n for n in (circuit.TempChannelName, *heat_calls) if n not in inputs]
        if missing:
            raise ValueError(
                f"{label} failed: circuit {circuit.Name!r} learns its setpoint on "
                f"{name!r}, whose InputChannelNames {inputs} lack {missing}."
            )
        strategy = derived_by_name[name].Strategy
        if strategy != "simple-falling-edge-setpoint":
            raise ValueError(
                f"{label} failed: circuit {circuit.Name!r} learns its setpoint on "
                f"{name!r}, whose Strategy is {strategy!r}, not "
                "'simple-falling-edge-setpoint'."
            )


def check_read_thermostat_channels(
    circuits: Iterable[Any],
    data_channels: Iterable[Any],
    sh_nodes: Iterable[Any],
    label: str,
) -> None:
    """A FromThermostat circuit's SetpointChannelName and TempChannelName
    each name a DataChannel captured by the node of the circuit's
    thermostat component."""
    captured_by = {c.Name: c.CapturedByNodeName for c in data_channels}
    component_of = {n.Name: n.ComponentId for n in sh_nodes}
    for circuit in circuits:
        if circuit.SetpointSource != ZoneSetpointSource.FromThermostat:
            continue
        for field, name in (
            ("SetpointChannelName", circuit.SetpointChannelName),
            ("TempChannelName", circuit.TempChannelName),
        ):
            if name is None:
                continue
            if name not in captured_by:
                raise ValueError(
                    f"{label} failed: circuit {circuit.Name!r} reads its thermostat, "
                    f"so {field} {name!r} SHALL be a channel in DataChannels."
                )
            component_id = component_of.get(captured_by[name])
            if component_id is None or component_id != circuit.Thermostat.ComponentId:
                raise ValueError(
                    f"{label} failed: circuit {circuit.Name!r} names {field} {name!r}, "
                    f"captured by {captured_by[name]!r}, which is not the node of the "
                    "circuit's thermostat component."
                )
