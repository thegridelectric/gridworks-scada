"""ZeroTenOutputer on the board DAC path: layout resolution (DacName against
the board record), the mux+DAC write choreography run through the REAL I2cBus
actor over the SimI2c register model, Multi-Write-only assertion (EEPROM
untouched) that reports the level, the boot EEPROM verify (mismatch ->
reprogram -> re-verify), dispatch -> Multi-Write of the commanded level ->
heartbeat re-assert of that level, and failure containment (a bus fault
becomes a throttled Glitch, never a crash). Plus House0's three outputs on
the same arm: each resolves against the Krida board record's DAC entries
(GP8403 modules at 94 and 95 on the real record, MCP4728s at the same
addresses on the sim record, no mux either way); the sim pair drives them
through the real bus actor over SimI2c, and the GP8403 write path is checked
byte for byte against what the multiplexer used to put on the wire.

The Nolan fixture carries `secondary-010v` on Dac2 channel C (power-on code
76 volts times ten = code 3040).
"""

import asyncio
import time
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import I2cBus
from actors.zero_ten_outputer import (
    DAC_FACTS,
    ZeroTenOutputer,
    code_from_volts_times_ten,
    volts_times_ten_from_code,
)
from drivers import gp8403
from gwproto.message import Message
from gwsproto.enums import I2cDacType, I2cOperation
from gwsproto.named_types import (
    ActuatorsReady,
    AnalogDispatch,
    I2cResult,
    I2cWriteReg,
    SingleReading,
)
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
NODE = "secondary-010v"
BUS_NAME = "i2c-bus"
MUX_ADDRESS = 0x70
DAC_ADDRESS = 0x60
DAC2_MUX_CHANNEL = 2
CHANNEL_C = 2
C_VOLTS_TIMES_TEN = 76  # the ops word's power-on level for secondary-010v
C_RAW = 3040  # 7.6 V of a 10.24 V full scale
DISPATCH_VOLTS_TIMES_TEN = 50
DISPATCH_RAW = 2000  # 5.0 V of a 10.24 V full scale

HOUSE0_PAIRS = {
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
    "house0-sim": (
        "gw.house0.sim.layout.json",
        "gw.house0.sim.operational.params.json",
    ),
}
# node -> (DAC address, channel index); the wiring the multiplexer had
HOUSE0_OUTPUTS = {
    "dist-010v": (94, 0),
    "primary-010v": (94, 1),
    "store-010v": (95, 0),
}
HOUSE0_POWER_ON = {"dist-010v": 20, "primary-010v": 40, "store-010v": 0}


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


def dispatch(out: ZeroTenOutputer, value: int) -> Message:
    """The boot boss commanding the outputer: wire source and FromHandle
    both the boss's, as the outputer requires."""
    boss = out.layout.node_by_handle(".".join(out.node.handle.split(".")[:-1]))
    return Message(
        Src=boss.name,
        Dst=out.name,
        Payload=AnalogDispatch(
            FromHandle=boss.handle,
            ToHandle=out.node.handle,
            AboutName=out.name,
            Value=value,
            TriggerId=str(uuid.uuid4()),
            UnixTimeMs=int(time.time() * 1000),
        ),
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
    assert out.power_on_code == C_RAW
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
    # the glitch names what the chip held and what the ops word declares
    assert f"read (0, 0, 0), ops ({C_RAW}, 1, 0)" in details[0]
    # a chip already carrying the declared defaults verifies silently
    out.warnings.clear()
    assert asyncio.run(out.verify_eeprom())
    assert out.warnings == []


def test_dispatch_sets_level_and_heartbeat_holds_it(rig) -> None:
    out, bus, sent = rig
    dac = bus.i2c.dacs[DAC2_MUX_CHANNEL]
    out.process_message(dispatch(out, DISPATCH_VOLTS_TIMES_TEN))
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
    out.process_message(dispatch(out, 101))
    assert out.target_code == C_RAW
    assert not out.wake.is_set()


def test_dispatch_full_scale_holds_at_the_top_code(rig) -> None:
    """10 V on the gw108's MCP4728 (10.24 V full scale) is code 4000; on a
    10 V full-scale chip it is the top code 4095, never 4096 (masked to 0)."""
    out, bus, sent = rig
    dac = bus.i2c.dacs[DAC2_MUX_CHANNEL]
    out.process_message(dispatch(out, 100))
    assert out.target_code == 4000
    asyncio.run(out.assert_target())
    assert dac.register[CHANNEL_C] == [4000, 1, 0]
    assert sent[-1].Value == 100
    for facts in DAC_FACTS.values():
        assert code_from_volts_times_ten(100, facts) <= facts.codes - 1
        assert volts_times_ten_from_code(code_from_volts_times_ten(100, facts), facts) == 100


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


@pytest.mark.parametrize("pair", sorted(HOUSE0_PAIRS))
def test_every_house0_output_resolves_against_the_krida_record(pair: str) -> None:
    """Both House0 fixtures: one component per output naming the board's
    DAC, no mux, the ops word's power-on level; the chip is the record's."""
    app = make_app(*HOUSE0_PAIRS[pair])
    chip = I2cDacType.Mcp4728 if pair == "house0-sim" else I2cDacType.Gp8403
    for name, (address, channel) in HOUSE0_OUTPUTS.items():
        out = ZeroTenOutputer(name, app)
        assert out.dac is app.hardware_layout.node(name).component
        assert out.dac.board_component is app.hardware_layout.scada_board()
        assert out.dac_type == chip
        assert out.dac_address == address
        assert out.channel == channel
        assert out.mux_address is None and out.mux_channel is None
        assert out.bus_node.name == BUS_NAME
        assert out.config.ChannelName == name
        level = HOUSE0_POWER_ON[name]
        assert out.power_on_code == round(
            level / 10 / out.facts.full_scale_volts * out.facts.codes
        )
        assert out.target_code == out.power_on_code
        assert out.monitored_names


def house0_sim_rig(name: str) -> tuple[ZeroTenOutputer, I2cBus, list]:
    app = make_app(*HOUSE0_PAIRS["house0-sim"])
    bus = I2cBus(BUS_NAME, app)
    out = ZeroTenOutputer(name, app)
    out.warnings = []
    out.send_warning = lambda summary, details="": out.warnings.append(summary)
    sent: list = []

    def out_send(dst, payload, src=None):
        if dst.name == BUS_NAME:
            bus.process_message(Message(Src=name, Dst=BUS_NAME, Payload=payload))
        else:
            sent.append(payload)

    out._send_to = out_send
    bus._send_to = lambda dst, payload, src=None: (
        out.process_message(Message(Src=BUS_NAME, Dst=name, Payload=payload))
        if dst.name == name
        else None
    )
    return out, bus, sent


def test_house0_sim_drives_muxless_dacs_through_the_bus() -> None:
    """The sim House0 board places its two MCP4728s directly on the bus;
    each output's boot verify and assert reach its own chip and channel,
    and nothing selects a mux."""
    for name, (address, channel) in HOUSE0_OUTPUTS.items():
        out, bus, sent = house0_sim_rig(name)
        assert bus.i2c.mux_address is None and bus.i2c.dacs == {}
        assert set(bus.i2c.muxless_dacs) == {94, 95}
        dac = bus.i2c.muxless_dacs[address]
        assert asyncio.run(out.verify_eeprom())
        assert dac.eeprom[channel] == [out.power_on_code, 1, 0]
        out.process_message(dispatch(out, DISPATCH_VOLTS_TIMES_TEN))
        asyncio.run(out.assert_target())
        assert dac.register[channel] == [DISPATCH_RAW, 1, 0]
        assert dac.eeprom[channel] == [out.power_on_code, 1, 0]
        assert sent[-1].ChannelName == name
        assert sent[-1].Value == DISPATCH_VOLTS_TIMES_TEN
        # a fresh sim chip holds no power-on level: verify reprograms it once
        assert out.warnings == ["i2c-dac-eeprom-reprogrammed"]
    # the other chip's channels are untouched by store-010v
    assert bus.i2c.muxless_dacs[94].register[0] == [0, 0, 0]


def test_gp8403_writes_the_multiplexer_wire_bytes() -> None:
    """The real House0 record's GP8403 arm: the range register once at boot,
    then the code word (code in bits 4-15, low byte first on the wire) to the
    channel's output register at the module address, no mux — byte for byte
    what the retired multiplexer's `write_word_data` calls put on the bus."""
    app = make_app(*HOUSE0_PAIRS["house0"])
    out = ZeroTenOutputer("primary-010v", app)  # Dfr1 channel B -> reg 0x04
    writes: list[I2cWriteReg] = []

    async def bus_ok(payload):
        writes.append(payload)
        return I2cResult(
            Bus=BUS_NAME,
            Operation=I2cOperation.WriteReg,
            Value=payload.Value,
            Success=True,
            UnixTimeMs=int(time.time() * 1000),
            TriggerId=payload.TriggerId,
        )

    out.bus_op = bus_ok
    out.warnings = []
    out.send_warning = lambda summary, details="": out.warnings.append(summary)
    sent: list = []
    out._send_to = lambda dst, payload, src=None: sent.append(payload)

    assert not out.facts.supports_power_on_store
    assert asyncio.run(out.verify_eeprom())  # nothing to verify, no bus op
    assert writes == []
    assert asyncio.run(out.prepare_chip())
    asyncio.run(out.assert_target())  # the ops power-on level: 4.0 V

    def wire(w: I2cWriteReg) -> tuple[int, int, int, int]:
        return (w.Address.I2cAddress, w.Address.RegisterIndex, w.Value >> 8, w.Value & 0xFF)

    code = round(40 / 10 / gp8403.FULL_SCALE_VOLTS * gp8403.CODES)
    assert code == 1638
    word = code << 4
    assert [wire(w) for w in writes] == [
        (94, gp8403.RANGE_REG, gp8403.RANGE_10V, 0x00),
        (94, gp8403.OUTPUT_REG[1], word & 0xFF, word >> 8),
    ]
    assert all(w.NumBytes == 2 for w in writes)
    assert sent[-1] == SingleReading(
        ChannelName="primary-010v", Value=40, ScadaReadTimeUnixMs=sent[-1].ScadaReadTimeUnixMs
    )
    assert not out.warnings

    # full scale: the top 12-bit code, not 4096 masked to 0 (beech 2026-09-13
    # wrote 0 V for 10 V)
    out.process_message(dispatch(out, 100))
    assert out.target_code == 4095
    asyncio.run(out.assert_target())
    assert wire(writes[-1]) == (94, gp8403.OUTPUT_REG[1], 0xF0, 0xFF)
    assert sent[-1].Value == 100
    assert not out.warnings


def test_outputer_reports_ready_on_start() -> None:
    """Each output is a required actuator: it tells the scada it is up
    when its heartbeat task starts."""
    app = make_app(*HOUSE0_PAIRS["house0-sim"])
    out = ZeroTenOutputer("dist-010v", app)
    sent: list = []
    out._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    out.services.add_task = lambda task: task.cancel()

    async def run():
        out.start()

    asyncio.run(run())
    assert sent == [(out.primary_scada.name, ActuatorsReady())]


# The 24-byte read i2ctransfer took on honeysuckle's Dac2 after the 2026-09-05
# bench boot: channel C input register and EEPROM both 0x8b 0xcc (code 3020,
# internal VREF, gain 1), the power-on code the layout declared then. The ops
# word now says 7.6 V (code 3040), so the same bytes are a mismatch.
BENCH_READ_2026_09_05 = [
    0xC0, 0x80, 0x00, 0xC8, 0x80, 0x00,
    0xD0, 0x80, 0x00, 0xD8, 0x80, 0x00,
    0xE0, 0x8B, 0xCC, 0xE8, 0x8B, 0xCC,
    0xF0, 0x80, 0x00, 0xF8, 0x80, 0x00,
]


def test_verify_reads_the_bench_chip_bytes(rig) -> None:
    """The comparison, fed the exact bytes a real MCP4728 returned, decodes
    the chip's (code, vref, gain) and reports the code-only mismatch against
    the ops level."""
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
    mismatch, detail = asyncio.run(out.read_eeprom_mismatch())
    assert mismatch is True
    assert detail == f"EEPROM (code, vref, gain) read (3020, 1, 0), ops ({C_RAW}, 1, 0)"
