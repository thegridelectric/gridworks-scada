"""The ZoneTempChannelResolution axiom body the layout words share."""

from typing import Any, Iterable


def check_zone_temp_channel_resolution(
    zones: Iterable[Any],
    data_channels: Iterable[Any],
    derived_channels: Iterable[Any],
    label: str,
) -> None:
    """Every zone's TempChannelName is the Name of a DataChannel or a
    DerivedChannel, and that channel carries temperature."""
    quantity_by_name = {c.Name: str(c.Quantity) for c in data_channels}
    quantity_by_name.update({c.Name: str(c.OutputQuantity) for c in derived_channels})
    for zone in zones:
        if zone.TempChannelName not in quantity_by_name:
            raise ValueError(
                f"{label} failed: zone {zone.Name!r} names TempChannelName "
                f"{zone.TempChannelName!r}, which is not a channel in DataChannels "
                "or DerivedChannels."
            )
        quantity = quantity_by_name[zone.TempChannelName]
        if quantity != "Temperature":
            raise ValueError(
                f"{label} failed: zone {zone.Name!r} names "
                f"{zone.TempChannelName!r}, whose quantity is {quantity}, not "
                "Temperature."
            )
