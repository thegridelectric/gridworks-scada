"""ZeroTenOutputer on the board DAC path: layout resolution (DacName against
the board record), the mux+DAC write choreography run through the REAL I2cBus
actor over the SimI2c register model, Multi-Write-only assertion (EEPROM
untouched) that reports the level, the boot EEPROM verify (mismatch ->
reprogram -> re-verify), dispatch -> Multi-Write of the commanded level ->
heartbeat re-assert of that level, and failure containment (a bus fault
becomes a throttled Glitch, never a crash). Plus the House0 path: a node with
no component forwards the dispatch to the DFR multiplexer.

The Nolan fixture carries `secondary-010v` on Dac2 channel C (power-on code
3020 = 7.55 V); the House0 sim fixture carries the three DFR outputs.
"""

import asyncio
import time
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import I2cBus
from actors.zero_ten_outputer import ZeroTenOutputer
from gwproto.message import Message
from gwsproto.enums import I2cOperation
from gwsproto.named_types import AnalogDispatch, I2cResult, SingleReading
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
NODE = "secondary-010v"
BUS_NAME = "i2c-bus"
MUX_ADDRESS = 0x70
DAC_ADDRESS = 0x60
DAC2_MUX_CHANNEL = 2
CHANNEL_C = 2
C_RAW = 3020  # the layout's PowerOnRawValue for channel C (7.55 V)
C_VOLTS_TIMES_TEN = 76
DISPATCH_VOLTS_TIMES_TEN = 50
DISPATCH_RAW = 2000  # 5.0 V of a 10.24 V full scale


def make_app(layout: str, ops: str) -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.fixture
def rig() -> tuple[ZeroTenOutputer, I2cBus, list]:
    app = make_app("gw.nolan.layout.json", "gw.nolan.operational.params.json")
    bus = I2cBus(BUS_NAME, app)
    out = ZeroTenOutputer(NODE, app)
    out.warnings = []
    out.send_warning = lambda summary, details="": out.warnings.append(summary)
    sent: list = []

    # direct cross-wiring: bus ops run the real bus handler; bus replies
    # resolve the outputer's pending futures; everything else is captured
    def out_send(dst, payload, src=None):
        if dst.name == BUS_NAME:
            bus.process_message(Message(Src=NODE, Dst=BUS_NAME, Payload=payload))
        else:
            sent.append(payload)

    out._send_to = out_send
    bus._send_to = lambda dst, payload, src=None: (
        out.process_message(Message(Src=BUS_NAME, Dst=NODE, Payload=payload))
        if dst.name == NODE
        else None
    )
    return out, bus, sent


def dispatch(out: ZeroTenOutputer, value: int) -> AnalogDispatch:
    boss = out.layout.node_by_handle(".".join(out.node.handle.split(".")[:-1]))
    return AnalogDispatch(
        FromHandle=boss.handle,
        ToHandle=out.node.handle,
        AboutName=out.name,
        Value=value,
        TriggerId=str(uuid.uuid4()),
        UnixTimeMs=int(time.time() * 1000),
    )


def test_registered_actor_instantiates(rig) -> None:
    out, _, _ = rig
    node = out.layout.node(NODE)
    assert node is not None
    assert node.component is out.dac
    assert out.monitored_names


def test_resolves_from_board_record(rig) -> None:
    out, _, _ = rig
    assert out.dac_address == DAC_ADDRESS
    assert out.mux_address == MUX_ADDRESS
    assert out.mux_channel == DAC2_MUX_CHANNEL
    assert out.channel == CHANNEL_C
    assert out.config.PowerOnRawValue == C_RAW
    assert out.target_code == C_RAW


def test_assert_target_is_multi_write_only_and_reports(rig) -> None:
    out, bus, sent = rig
    dac = bus.i2c.dacs[DAC2_MUX_CHANNEL]
    asyncio.run(out.assert_target())
    assert dac.register[CHANNEL_C] == [C_RAW, 1, 0]
    assert dac.register[0] == [0, 0, 0]  # the unwired channels are untouched
    # Multi-Write never touches EEPROM — the wear/default-clobber guard
    assert dac.eeprom[CHANNEL_C] == [0, 0, 0]
    assert not out.warnings
    assert [r for r in sent if isinstance(r, SingleReading)] == [
        r for r in sent
    ]
    assert sent[-1].ChannelName == NODE
    assert sent[-1].Value == C_VOLTS_TIMES_TEN


def test_boot_verify_reprograms_then_stays_clean(rig) -> None:
    out, bus, _ = rig
    dac = bus.i2c.dacs[DAC2_MUX_CHANNEL]
    details: list[str] = []
    out.send_warning = lambda summary, details_="", **kw: (
        out.warnings.append(summary),
        details.append(kw.get("details", details_)),
    )
    assert asyncio.run(out.verify_eeprom())
    assert dac.eeprom[CHANNEL_C] == [C_RAW, 1, 0]
    assert dac.register[CHANNEL_C] == [C_RAW, 1, 0]
    assert out.warnings == ["i2c-dac-eeprom-reprogrammed"]
    # the glitch names what the chip held and what the layout declares
    assert f"read (0, 0, 0), layout ({C_RAW}, 1, 0)" in details[0]
    # a chip already carrying the declared defaults verifies silently
    out.warnings.clear()
    assert asyncio.run(out.verify_eeprom())
    assert out.warnings == []


def test_dispatch_sets_level_and_heartbeat_holds_it(rig) -> None:
    out, bus, sent = rig
    dac = bus.i2c.dacs[DAC2_MUX_CHANNEL]
    out.process_message(
        Message(Src="lc", Dst=NODE, Payload=dispatch(out, DISPATCH_VOLTS_TIMES_TEN))
    )
    assert out.target_code == DISPATCH_RAW
    assert out.wake.is_set()
    asyncio.run(out.assert_target())
    assert dac.register[CHANNEL_C] == [DISPATCH_RAW, 1, 0]
    assert dac.eeprom[CHANNEL_C] == [0, 0, 0]
    assert sent[-1].Value == DISPATCH_VOLTS_TIMES_TEN
    # the chip forgets; the heartbeat re-asserts the LAST COMMANDED level,
    # not the power-on one
    dac.power_on_reset()
    asyncio.run(out.assert_target())
    assert dac.register[CHANNEL_C] == [DISPATCH_RAW, 1, 0]


def test_dispatch_out_of_range_is_ignored(rig) -> None:
    out, _, _ = rig
    out.process_message(Message(Src="lc", Dst=NODE, Payload=dispatch(out, 101)))
    assert out.target_code == C_RAW
    assert not out.wake.is_set()


def test_bus_fault_contained_throttled_and_heals(rig) -> None:
    out, bus, _ = rig
    bus.i2c.inject_fault(MUX_ADDRESS, count=None)
    asyncio.run(out.assert_target())
    assert out.warnings == ["i2c-dac-write-failed"]
    asyncio.run(out.assert_target())
    assert len(out.warnings) == 1  # once per failure streak
    bus.i2c.clear_faults()
    asyncio.run(out.assert_target())
    assert bus.i2c.dacs[DAC2_MUX_CHANNEL].register[CHANNEL_C] == [C_RAW, 1, 0]
    bus.i2c.inject_fault(MUX_ADDRESS, count=None)
    asyncio.run(out.assert_target())
    assert len(out.warnings) == 2  # a new streak warns again


def test_verify_read_failure_warns_and_returns_false(rig) -> None:
    out, bus, _ = rig
    bus.i2c.inject_fault(DAC_ADDRESS, count=None)
    assert not asyncio.run(out.verify_eeprom())
    assert out.warnings == ["i2c-dac-eeprom-read-failed"]


def test_house0_output_forwards_to_dfr_multiplexer() -> None:
    app = make_app("gw.house0.sim.layout.json", "gw.house0.sim.operational.params.json")
    out = ZeroTenOutputer("dist-010v", app)
    assert out.dac is None
    assert out.dfr_multiplexer is not None
    assert out.monitored_names == []
    sent: list = []
    out._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    out.process_message(
        Message(Src="auto", Dst="dist-010v", Payload=dispatch(out, DISPATCH_VOLTS_TIMES_TEN))
    )
    (dst, forwarded), = sent
    assert dst == out.dfr_multiplexer.name
    assert isinstance(forwarded, AnalogDispatch)
    assert forwarded.FromHandle == out.node.handle
    assert forwarded.ToHandle == out.dfr_multiplexer.handle
    assert forwarded.Value == DISPATCH_VOLTS_TIMES_TEN


# The 24-byte read i2ctransfer took on honeysuckle's Dac2 after the 2026-09-05
# bench boot: channel C input register and EEPROM both 0x8b 0xcc (code 3020,
# internal VREF, gain 1), the layout's PowerOn values for secondary-010v.
BENCH_READ_2026_09_05 = [
    0xC0, 0x80, 0x00, 0xC8, 0x80, 0x00,
    0xD0, 0x80, 0x00, 0xD8, 0x80, 0x00,
    0xE0, 0x8B, 0xCC, 0xE8, 0x8B, 0xCC,
    0xF0, 0x80, 0x00, 0xF8, 0x80, 0x00,
]


def test_verify_accepts_the_bench_chip_read(rig) -> None:
    """The comparison, fed the exact bytes a real MCP4728 returned with the
    declared power-on values in EEPROM, reports no mismatch."""
    out, _, _ = rig

    async def chip_read(payload):
        return I2cResult(
            Bus=BUS_NAME,
            Operation=I2cOperation.ReadBytes,
            Bytes=BENCH_READ_2026_09_05,
            Success=True,
            UnixTimeMs=int(time.time() * 1000),
            TriggerId=payload.TriggerId,
        )

    out.muxed_op = chip_read
    assert asyncio.run(out.read_eeprom_mismatch()) == (False, "")
