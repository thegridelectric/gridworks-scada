# actors/procedural/pump_power.py

"""What a circulator's power draw says about it, for the pump monitors and
doctors. A pump drawing more than the stall ceiling is running whatever its
loop's flow meter reads; a flow meter that reads no flow under a running
pump is the meter's fault, and the glitch goes on the meter's node."""

from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.enums import CirculatorRole

# A stalled circulator hums at 1 to 5 W (beech store 2026-01-22, oak store
# 2026-02-02, elm dist 2026-01-13 and 01-15); the lowest running draw of a
# store or dist pump at its deployed level is 7 W (beech dist at 3.5 V).
# Above the ceiling the pump is running. At or below it the flow meter
# decides, as it did before the ceiling existed, so a pump that runs at
# 4 to 5 W (oak dist at 5.0 V) keeps its flow-based verdict. A per-model
# figure from the circulator's device type retires this constant.
STALL_CEILING_W = 6


def power_channel_name(layout: HydronicLayout, role: CirculatorRole) -> str | None:
    """The power channel of the layout's circulator in this role, or None
    when the layout has no such circulator or it reports no power."""
    for circulator in layout.hydronic.Circulators:
        if circulator.Role == role:
            return circulator.PowerChannelName
    return None


def meter_node_name(layout: HydronicLayout, flow_channel_name: str) -> str:
    """The node that captures a flow channel: the BTU meter the glitch names."""
    channel = layout.channel(flow_channel_name)
    if channel is None:
        raise ValueError(f"layout has no channel {flow_channel_name!r}")
    return channel.CapturedByNodeName


def is_running(power_w: int | None) -> bool:
    """True when the pump's latest power reading puts it above the stall ceiling."""
    return power_w is not None and power_w > STALL_CEILING_W
