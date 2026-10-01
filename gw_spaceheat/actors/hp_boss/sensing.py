"""The heat pump's sensing surface: what the scada knows about each kind
of heat pump, by the hp-odu component's DeviceType, and how its channels
show what the unit is doing.

Interim. The tables here are the hand-kept copy of what the heat pump's
device-type record (hp.device.type.gt) will carry; the record retires
them. Two things are known to be wrong with the shape: the running-above /
stopped-below power pair does not handle defrost (the draw falls while the
unit is still in a cycle and the pump must keep running), and no heat-pump
temperature sensor is trusted yet; hp-ewt, hp-lwt, the primary and
secondary flows and the secondary ewt and lwt join this surface when their
sensors, some of them picos, earn trust.

Where this converges: hp-boss runs a sensed machine of the unit's state,
Off, Charging, Defrost, and Unknown while blind, derived here once from
the power channels and later confirmed by lift, reported as a machine
state like every other machine in the scada, and every consumer (the pump
posture, the cold logic, the sieg strategy, which still carries its own
idle-draw line in sieg_loop/strat_protect.py) reads that state rather
than the raw draw. The state is the unit's, never a compressor's: some
units have two compressors, and nothing outside this package knows how
many.
"""

from typing import Literal, NamedTuple


class HpTraits(NamedTuple):
    """One kind of heat pump in its power draw: the outdoor-unit draw
    above which the unit is running and the secondary pump must run, the
    draw below which it has stopped, and how long before an on-peak window
    opens the call opens, so the unit has stopped drawing by the
    boundary."""

    on_above_w: int
    off_below_w: int
    call_open_lead_s: int


HP_TRAITS: dict[str, HpTraits] = {
    "SamsungAE055FCYDCG": HpTraits(500, 80, 120),
    "SimHpOdu": HpTraits(500, 80, 120),
}
"""By the hp-odu component's DeviceType. The only source of these values:
a layout whose heat pump has no row cannot run the Nolan heating machine. Hand-kept
until hp.device.type.gt carries the three values, which retires this
table. The Samsung lead is provisional: the unit's stop lag is unmeasured
(the spruce journal shows stops within a minute of the call opening and
one at four minutes on a young run)."""


class DefrostSignature(NamedTuple):
    """How a heat pump shows it is defrosting: which draw to watch (the
    indoor unit alone, or indoor + outdoor) and the watt line it falls
    under while the compressor reverses."""

    draw: Literal["idu", "total"]
    max_w: int


DEFROST_SIGNATURES: dict[str, DefrostSignature] = {
    "LGARUM048GSS5": DefrostSignature("total", 8400),
    "SamsungAE055FCYDCG": DefrostSignature("idu", 4000),  # the hydro-kit pairing (fir)
}
"""By the hp-odu component's DeviceType. A unit not listed has no known
signature and is never judged in defrost. Hand-kept until
hp.device.type.gt carries the signature, which retires this table."""
