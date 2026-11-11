"""A 0-10 V output of a scada board's DAC, as its actor drives it. Where the
output sits (DAC address, mux position, channel, chip) is resolved once from
the board's device-type record, and the choice of chip is made here: the
output's actor holds none of it.
"""

import asyncio
import uuid
from typing import Any, NamedTuple, Optional

from gwsproto.data_classes.components import I2cDacOutputComponent
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import I2cDacChannel, I2cDacType
from gwsproto.named_types import (
    I2cReadBytes,
    I2cRegAddress,
    I2cResult,
    I2cWriteByte,
    I2cWriteReg,
)

from bus_talk import BusTalk, the_bus_node
from drivers import gp8403, mcp4728
from plant import Heard, LevelDrive, LevelSet, Prepared, Said, Send

CHANNEL_INDEX = {
    I2cDacChannel.A: 0,
    I2cDacChannel.B: 1,
    I2cDacChannel.C: 2,
    I2cDacChannel.D: 3,
}


class DacFacts(NamedTuple):
    """What driving a level needs from the choice of DAC chip: the terminal
    volts at full code and whether the chip stores a power-on value. Driver
    facts, keyed on the board record's DacType; not vocabulary."""

    codes: int
    full_scale_volts: float
    supports_power_on_store: bool


DAC_FACTS: dict[I2cDacType, DacFacts] = {
    I2cDacType.Mcp4728: DacFacts(
        mcp4728.CODES, mcp4728.FULL_SCALE_VOLTS, mcp4728.SUPPORTS_POWER_ON_STORE
    ),
    I2cDacType.Gp8403: DacFacts(
        gp8403.CODES, gp8403.FULL_SCALE_VOLTS, gp8403.SUPPORTS_POWER_ON_STORE
    ),
}


def code_from_volts_times_ten(value: int, facts: DacFacts) -> int:
    """The code that drives `value` (volts times ten) at the terminal,
    clamped to the chip's top code: full scale rounds to `codes`, one past
    the last 12-bit code, and the encoders mask that to 0."""
    return min(
        round(value / 10 / facts.full_scale_volts * facts.codes), facts.codes - 1
    )


def volts_times_ten_from_code(code: int, facts: DacFacts) -> int:
    return round(code / facts.codes * facts.full_scale_volts * 10)


class DacOutput(NamedTuple):
    """Where one 0-10 V output sits on its board. Interior to the scada and
    never serialised: no word carries a resolved DAC channel."""

    bus_node: ShNode
    dac_address: int
    dac_type: I2cDacType
    channel: int
    channel_letter: I2cDacChannel
    mux_address: Optional[int]
    mux_channel: Optional[int]


def resolve_dac_output(layout: HydronicLayout, node: ShNode) -> DacOutput:
    """DacName resolved against the component's own board record: the
    record's DAC list holds the physical address and mux position, which
    the layout never restates."""
    component = node.component
    assert isinstance(component, I2cDacOutputComponent)
    config = component.gt.ConfigList[0]
    channel = CHANNEL_INDEX[config.DacChannel]
    record = component.board_component.device_type
    dac = next((d for d in record.Dacs if d.DacName == component.gt.DacName), None)
    if dac is None:
        raise ValueError(
            f"{node.name}: board record {record.DeviceType} has no DAC "
            f"named {component.gt.DacName}"
        )
    if channel >= dac.Channels:
        raise ValueError(
            f"{node.name}: channel {config.DacChannel.value} is beyond the "
            f"{dac.Channels} channels of DAC {dac.DacName}"
        )
    mux_address: Optional[int] = None
    mux_channel: Optional[int] = None
    if dac.MuxName is not None:
        mux = next(m for m in record.Muxes if m.MuxName == dac.MuxName)
        mux_address = mux.I2cAddress
        mux_channel = dac.MuxChannel
    return DacOutput(
        bus_node=the_bus_node(layout, node.name),
        dac_address=dac.I2cAddress,
        dac_type=dac.DacType,
        channel=channel,
        channel_letter=config.DacChannel,
        mux_address=mux_address,
        mux_channel=mux_channel,
    )


class I2cDacDrive(LevelDrive):
    """One channel of a board DAC, driven through the bus actor. The chip
    branch is here: a chip that stores a power-on value (MCP4728) has its
    EEPROM verified against the power-on level once after boot and
    reprogrammed only on a mismatch (Single Write: the one EEPROM-touching
    path); a chip that stores nothing (GP8403) has its output range set
    once after boot and sits at the chip default until the first set."""

    def __init__(self, at: DacOutput) -> None:
        self.at = at
        self.facts = DAC_FACTS[at.dac_type]
        self.bus = BusTalk(at.bus_node)

    def attach(self, send: Send) -> None:
        self.bus.attach(send)

    def hears(self, payload: Any) -> Heard:
        return Heard.Taken if self.bus.hears(payload) else Heard.NotMine

    def code(self, level: int) -> int:
        return code_from_volts_times_ten(level, self.facts)

    async def muxed_op(self, payload: I2cWriteReg | I2cReadBytes) -> I2cResult | None:
        """Select this DAC's mux channel (when muxed), then run the op."""
        if self.at.mux_address is not None and self.at.mux_channel is not None:
            select = await self.bus.op(
                I2cWriteByte(
                    Bus=self.at.bus_node.name,
                    I2cAddress=self.at.mux_address,
                    Value=1 << self.at.mux_channel,
                    TriggerId=str(uuid.uuid4()),
                )
            )
            if select is None or not select.Success:
                return select
        return await self.bus.op(payload)

    async def write_register(self, register: int, first: int, second: int) -> tuple[bool, str]:
        """One two-byte write to a register of this DAC, `first` then
        `second` on the wire. (ok, detail)."""
        result = await self.muxed_op(
            I2cWriteReg(
                Bus=self.at.bus_node.name,
                Address=I2cRegAddress(I2cAddress=self.at.dac_address, RegisterIndex=register),
                NumBytes=2,
                Value=(first << 8) | second,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return False, "bus op timeout"
        if not result.Success:
            return False, result.Error or "unknown bus error"
        return True, ""

    def data_bits(self) -> tuple[int, int]:
        return (
            mcp4728.VREF_BIT[mcp4728.POWER_ON_VREF],
            mcp4728.gain_bit(mcp4728.POWER_ON_GAIN),
        )

    async def write_code(self, code: int, command_base: int) -> tuple[bool, str]:
        """MCP4728: one write of `code` to this channel in the given command
        family. (ok, detail)."""
        vref, gain = self.data_bits()
        hi, lo = mcp4728.encode_data(code, vref, gain)
        return await self.write_register(mcp4728.command(command_base, self.at.channel), hi, lo)

    async def write_output(self, code: int) -> tuple[bool, str]:
        """GP8403: one write of `code` to this channel's output register.
        (ok, detail)."""
        first, second = gp8403.word_bytes(gp8403.encode_word(code))
        return await self.write_register(gp8403.OUTPUT_REG[self.at.channel], first, second)

    async def set(self, level: int) -> LevelSet:
        """The chip's routine level write: the one that never touches a
        stored power-on value."""
        code = self.code(level)
        held = volts_times_ten_from_code(code, self.facts)
        if self.at.dac_type == I2cDacType.Mcp4728:
            ok, detail = await self.write_code(code, mcp4728.MULTI_WRITE_BASE)
        else:
            ok, detail = await self.write_output(code)
        if not ok:
            said = Said("i2c-dac-write-failed", f"volts x10 {held} (code {code}): {detail}", True)
            return LevelSet(None, (said,))
        return LevelSet(held, ())

    async def prepare(self, power_on_level: int) -> Prepared:
        if self.at.dac_type == I2cDacType.Mcp4728:
            return await self.verify_eeprom(self.code(power_on_level))
        return await self.set_range()

    async def set_range(self) -> Prepared:
        """GP8403: the chip does not keep its output range across a
        power-up."""
        ok, detail = await self.write_register(
            gp8403.RANGE_REG, *gp8403.word_bytes(gp8403.RANGE_10V)
        )
        if not ok:
            return Prepared(False, (Said("i2c-dac-range-set-failed", detail, True),), "")
        return Prepared(True, (), "output range set to 0-10 V")

    async def read_eeprom_mismatch(self, power_on_code: int) -> tuple[bool | None, str]:
        """Whether the channel's EEPROM differs from the power-on code (and
        the driver's reference and gain), or (None, detail) when the read
        itself failed."""
        result = await self.muxed_op(
            I2cReadBytes(
                Bus=self.at.bus_node.name,
                I2cAddress=self.at.dac_address,
                NumBytes=mcp4728.READ_LEN,
                TriggerId=str(uuid.uuid4()),
            )
        )
        if result is None:
            return None, "bus op timeout"
        if not result.Success or result.Bytes is None:
            return None, result.Error or "unknown bus error"
        vref, gain = self.data_bits()
        hi, lo = mcp4728.eeprom_data(result.Bytes, self.at.channel)
        expected = (power_on_code, vref, gain)
        read = mcp4728.decode_data(hi, lo)
        if read == expected:
            return False, ""
        return True, f"EEPROM (code, vref, gain) read {read}, ops {expected}"

    async def verify_eeprom(self, power_on_code: int) -> Prepared:
        """Read -> compare to the power-on code -> reprogram a mismatch
        (Single Write) -> re-verify."""
        mismatch, mismatch_detail = await self.read_eeprom_mismatch(power_on_code)
        if mismatch is None:
            return Prepared(
                False, (Said("i2c-dac-eeprom-read-failed", mismatch_detail, True),), ""
            )
        if not mismatch:
            return Prepared(True, (), "EEPROM verified against the ops power-on level")
        await self.write_code(power_on_code, mcp4728.SINGLE_WRITE_BASE)
        # let the chip's EEPROM write cycle complete before the next
        # command or the re-read sees stale data
        await asyncio.sleep(mcp4728.EEPROM_WRITE_TIME_S + 0.01)
        still_mismatch, detail = await self.read_eeprom_mismatch(power_on_code)
        channel = self.at.channel_letter.value
        if still_mismatch is False:
            said = Said(
                "i2c-dac-eeprom-reprogrammed",
                f"channel {channel} {mismatch_detail}; reprogrammed and re-verified",
                False,
            )
            return Prepared(True, (said,), "")
        said = Said(
            "i2c-dac-eeprom-verify-failed",
            f"channel {channel} mismatched; after reprogram still bad ({detail})",
            False,
        )
        return Prepared(False, (said,), "")


class KeptLevelDrive(LevelDrive):
    """A simulated board's 0-10 V output: it holds whatever level it is
    set. No level crosses to the plant, which is told what its pumps do by
    the relays."""

    async def prepare(self, power_on_level: int) -> Prepared:
        return Prepared(True, (), "")

    async def set(self, level: int) -> LevelSet:
        return LevelSet(level, ())
