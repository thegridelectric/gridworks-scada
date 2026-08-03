"""I2cDacWriter tests: the mux+DAC write choreography, failure containment
(a bus fault becomes a Glitch, never a crash), and heartbeat re-assert.

The actor is not layout-connected yet (no actor.class value); the fixture
injects a NoActor node and constructs the actor directly on it.
"""

import json
import time
import uuid
from pathlib import Path

import pytest

from actors.i2c_dac_writer import I2cDacWriter
from gwsproto.named_types import AnalogDispatch
from gwproto.message import Message
from scada_app import ScadaApp

DAC_NODE = "dac-writer"
MUX_CHANNEL = 3
DAC_CHANNEL = 2  # channel_c


class FakeMuxedDac:
    """Captures mux selects and DAC block writes; can fail on demand."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, int, list[int] | int]] = []
        self.fail = False

    def write_byte(self, addr: int, value: int) -> None:
        if self.fail:
            raise OSError("simulated mux write timeout")
        self.writes.append(("mux", addr, value))

    def write_i2c_block_data(self, addr: int, cmd: int, data: list[int]) -> None:
        if self.fail:
            raise OSError("simulated dac write failure")
        self.writes.append(("dac", addr, [cmd, *data]))


@pytest.fixture
def writer(tmp_path: Path) -> I2cDacWriter:
    settings = ScadaApp.get_settings()
    settings.is_simulated = True
    layout_dict = json.loads(Path(settings.paths.hardware_layout).read_text())
    layout_dict["ShNodes"].append(
        {
            "Name": DAC_NODE,
            "ActorClass": "NoActor",
            "Handle": f"auto.{DAC_NODE}",
            "ShNodeId": str(uuid.uuid4()),
            "TypeName": "spaceheat.node.gt",
            "Version": "303",
        }
    )
    layout_path = tmp_path / "layout-with-dac.json"
    layout_path.write_text(json.dumps(layout_dict))
    settings.paths.hardware_layout = layout_path
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    actor = I2cDacWriter(
        DAC_NODE, app, mux_channel=MUX_CHANNEL, dac_channel=DAC_CHANNEL
    )
    actor.is_simulated = False
    actor.i2c = FakeMuxedDac()
    actor.warnings = []
    actor.send_warning = lambda summary, details="": actor.warnings.append(summary)
    return actor


def dispatch(value: int) -> Message:
    return Message(
        Src="auto",
        Dst=DAC_NODE,
        Payload=AnalogDispatch(
            FromHandle="auto",
            ToHandle=f"auto.{DAC_NODE}",
            AboutName=DAC_NODE,
            Value=value,
            TriggerId=str(uuid.uuid4()),
            UnixTimeMs=int(time.time() * 1000),
        ),
    )


def test_dispatch_writes_mux_then_dac(writer: I2cDacWriter) -> None:
    result = writer.process_message(dispatch(65))
    assert result.is_ok()
    assert writer.last_commanded_raw == 65 * writer.RAW_PER_PERCENT  # 2600
    kinds = [w[0] for w in writer.i2c.writes]
    assert kinds == ["mux", "dac"]
    _, mux_addr, mux_val = writer.i2c.writes[0]
    assert mux_addr == writer.MUX_ADDRESS
    assert mux_val == 1 << MUX_CHANNEL
    _, dac_addr, dac_bytes = writer.i2c.writes[1]
    assert dac_addr == writer.DAC_ADDRESS
    cmd, hi, lo = dac_bytes
    assert cmd == writer._SINGLE_WRITE_CMD | (DAC_CHANNEL << 1)
    raw = ((hi & 0x0F) << 8) | lo
    assert raw == 2600
    assert hi & 0x80  # internal vref bit
    assert not writer.warnings


def test_write_failure_is_contained(writer: I2cDacWriter) -> None:
    writer.i2c.fail = True
    result = writer.process_message(dispatch(65))
    assert result.is_ok()  # a bus fault never crashes the actor
    assert writer.warnings == ["i2c-dac-write-failed"]
    assert writer.last_commanded_raw == 2600  # retained for re-assert


def test_reassert_after_failure_heals(writer: I2cDacWriter) -> None:
    writer.i2c.fail = True
    writer.process_message(dispatch(65))
    assert not writer.i2c.writes
    writer.i2c.fail = False
    assert writer._write_dac()  # the heartbeat's re-assert call
    kinds = [w[0] for w in writer.i2c.writes]
    assert kinds == ["mux", "dac"]


def test_out_of_range_and_wrong_target_ignored(writer: I2cDacWriter) -> None:
    msg = dispatch(101)
    writer.process_message(msg)
    assert writer.last_commanded_raw is None
    wrong = dispatch(50)
    wrong.Payload.ToHandle = "auto.someone-else"
    writer.process_message(wrong)
    assert writer.last_commanded_raw is None
    assert not writer.i2c.writes
