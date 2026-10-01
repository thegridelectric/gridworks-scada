"""The heat pump's sensing surface: what the scada knows about each kind
of heat pump, by the hp-odu component's DeviceType, and how its channels
show what the unit is doing.

Channels or machine states, the litmus test. A channel carries a value
sampled over time: a reading is a time and a value with no cause, it has
an age, and a consumer reasons about its value and its freshness. A
derived channel is a channel whose value is a function of other channels'
readings by a strategy the layout declares (a sum, a threshold, a
difference), with no memory beyond its inputs. A machine state carries a
judgment with memory: entered by a transition with a trigger and a cause,
held until the next transition, able to carry hysteresis, a blind state
and a timer. So: if the value now is a pure function of other readings
now, or of a declared window of them, it is a derived channel; if telling
it requires remembering what it was, a latch, a timer, a cause, it is a
machine. Everything the scada commands is a machine. Something observed
is either, by the test; being an observation does not make it a channel.

This surface supplies both. The unit's state, Off, Charging, Defrost, and
Unknown while blind, is a machine: it holds across the draw's noise with
a running-above / stopped-below pair, a defrost is told by the draw
falling while the state is Charging, and blind is a timer on the inputs'
age. Its derived channels are the water side: lift (hp-lwt minus hp-ewt)
and heat output (primary flow times lift), published as soon as the
channels exist; whether the machine acts on them is the trust question
below, not whether they are derived. Power is
not this surface's to derive: the power meter owns every power channel
and every channel derived from power, since transactive power is the
whole electrical load, the resistive elements as much as the heat pump.
This machine reads the power meter's channels; it does not make them.

Interim. The tables below are the hand-kept copy of what the heat pump's
device-type record (hp.device.type.gt) will carry; the record retires
them. Two things are known to be wrong with the shape: the running-above /
stopped-below power pair does not handle defrost (the draw falls while the
unit is still in a cycle and the pump must keep running), and no heat-pump
temperature sensor is trusted yet; hp-ewt, hp-lwt, the primary and
secondary flows and the secondary ewt and lwt join this surface when their
sensors, some of them picos, earn trust. The machine above is not built;
today the Nolan heating machine and House0's plant judgment read these
tables directly, and the sieg loop carries its own idle-draw line in
sieg_loop/strat_protect.py. The state is the unit's, never a compressor's:
some units have two compressors, and nothing outside this package knows
how many.
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
