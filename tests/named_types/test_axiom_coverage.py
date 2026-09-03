"""Every sema axiom on a gwsproto type is a gwsproto obligation, twice over.

gwsproto types are hand-written twins of sema words and cannot vendor the sema
snapshot, so nothing regenerates their validators. This test closes the gap
structurally: for every exported gwsproto type whose sema word declares
axioms,

1. the class carries `check_axiom_<n>` for exactly the axiom numbers sema
   declares (no missing port, no stale validator, no `# Implement Axiom`
   stub), and
2. `tests/named_types/` holds a test function named
   `test_<type_snake>_axiom_<n>[_<clause>][_<why>]` for each axiom — a
   counterexample the validator must reject.

The allowlists are the checked-in record of KNOWN debt, matched exactly so
the record stays honest: fixing an item without removing it here fails, and
new debt fails. They should shrink to empty.

Requires the sibling sema checkout; skips if absent."""

import inspect
import re
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2] / "packages" / "gridworks-scada-protocol"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import gwsproto_sema_conformance as conformance  # noqa: E402

SEMA_ROOT = conformance.DEFAULT_SEMA
TESTS_DIR = Path(__file__).parent

# --- KNOWN debt: sema axioms with no check_axiom_<n> on the gwsproto class ---
KNOWN_UNPORTED_AXIOMS: set[str] = {
    "gw.house0.layout/000:12",
    "gw.nolan.layout/000:10",
    "new.command.tree/002:2",
}

# --- KNOWN debt: check_axiom_<n> methods sema no longer declares ---
KNOWN_STALE_VALIDATORS: set[str] = {
    "fsm.event/000:2",
    "gw1.tank.temp.calibration.map/001:1",
    "heating.forecast/000:2",
    "pico.btu.meter.component.gt/000:2",
}

# --- KNOWN debt: sema axioms with no rejecting test in tests/named_types ---
KNOWN_UNTESTED_AXIOMS: set[str] = {
    "ads111x.based.component.gt/000:1",
    "ads111x.based.component.gt/000:2",
    "bid/000:1",
    "bid/000:2",
    "bid/000:3",
    "bid/000:4",
    "channel.readings/002:1",
    "derived.channel.gt/002:1",
    "derived.channel.gt/002:2",
    "derived.channel.gt/002:3",
    "derived.channel.gt/002:4",
    "dfr.component.gt/000:1",
    "electric.meter.component.gt/001:1",
    "energy.instruction/000:1",
    "energy.instruction/000:2",
    "fsm.atomic.report/001:1",
    "fsm.atomic.report/001:2",
    "fsm.event/000:1",
    "g.node.gt/006:1",
    "g.node.gt/006:2",
    "g.node.gt/006:3",
    "g.node.gt/006:4",
    "g.node.gt/006:5",
    "g.node.gt/006:6",
    "gpio.relay.component.gt/000:1",
    "gw.house0.layout/000:1",
    "gw.house0.layout/000:4",
    "gw.house0.layout/000:5",
    "gw.house0.layout/000:12",
    "gw.house0.operational.params/000:1",
    "gw.house0.operational.params/000:2",
    "gw.hydronic/000:1",
    "gw.nolan.layout/000:10",
    "gw.nolan.operational.params/000:1",
    "gw.nolan.operational.params/000:2",
    "gw.tou.window/000:1",
    "gw.tou.window/000:2",
    "gw1.scada.device.type.gt/000:1",
    "gw1.scada.device.type.gt/000:2",
    "gw1.scada.device.type.gt/000:3",
    "gw1.scada.device.type.gt/000:4",
    "gw1.unit.quantity.projection/000:1",
    "gw1.zone.call.circuit/000:1",
    "gw1.zone.call.circuit/000:2",
    "gw1.zone.thermostat/000:1",
    "heating.forecast/000:1",
    "i2c.dac.capability/000:1",
    "i2c.dac.channel.config/000:1",
    "i2c.dac.writer.component.gt/000:1",
    "i2c.expander/000:1",
    "i2c.multichannel.dt.relay.component.gt/004:1",
    "i2c.multichannel.dt.relay.component.gt/004:2",
    "i2c.read.reg/000:1",
    "i2c.result/001:1",
    "i2c.thermistor.reader.component.gt/000:1",
    "i2c.write.bit/000:1",
    "i2c.write.byte/000:1",
    "i2c.write.reg/000:1",
    "i2c.write.reg/000:2",
    "layout.lite/013:1",
    "layout.lite/013:2",
    "layout.lite/013:3",
    "layout.lite/013:4",
    "machine.states/000:1",
    "machine.states/000:2",
    "new.command.tree/002:2",
    "pico.flow.module.component.gt/001:1",
    "pico.tank.module.component.gt/012:1",
    "pico.tank.module.component.gt/012:2",
    "pico.tank.module.component.gt/012:3",
    "relay.control.config/000:1",
    "relay.control.config/000:2",
    "relay.control.config/000:3",
    "scada.control.capabilities/001:1",
    "scada.control.capabilities/001:2",
    "scada.control.capabilities/001:3",
    "scada.control.capabilities/001:4",
    "sim.dac.writer.component.gt/000:1",
    "sim.pico.tank.module.component.gt/001:1",
    "sim.pico.tank.module.component.gt/001:2",
    "sim.pico.tank.module.component.gt/001:3",
    "sim.relay.component.gt/000:1",
    "single.machine.state/000:1",
    "spaceheat.node.gt/302:1",
    "spaceheat.node.gt/302:2",
    "spaceheat.telemetry.quantity.projection/000:1",
    "synced.readings/000:1",
    "ticklist.hall/101:1",
    "ticklist.reed/101:1",
    "weather.forecast/000:1",
    "weather.forecast/000:2",
}


def snake(type_name: str) -> str:
    return type_name.replace(".", "_")


@pytest.fixture(scope="module")
def sema_axioms() -> dict[str, tuple[type, str, list[int]]]:
    """TypeName -> (class, version, sorted sema axiom numbers) for every
    exported gwsproto type with a sema word (axiom list possibly empty, so a
    validator sema never declared is caught as stale)."""
    if not (SEMA_ROOT / "definitions" / "registry.yaml").exists():
        pytest.skip(f"sema checkout not found at {SEMA_ROOT}")
    classes = conformance.gwsproto_classes()
    wanted = {
        f"type::{tn}": f"definitions/types/{tn}/{ver}.yaml"
        for tn, (_, ver) in classes.items()
        if ver
    }
    schemas = conformance.load_sema(SEMA_ROOT, wanted)["schemas"]
    out = {}
    for tn, (cls, ver) in classes.items():
        schema = schemas.get(f"type::{tn}")
        if not schema:
            continue
        axioms = (schema.get("x-gridworks") or {}).get("axioms") or []
        out[tn] = (cls, ver, sorted(int(a["number"]) for a in axioms))
    return out


def implemented_axioms(cls: type) -> tuple[list[int], bool]:
    src = inspect.getsource(cls)
    nums = sorted(int(n) for n in re.findall(r"def check_axiom_(\d+)\b", src))
    return nums, "# Implement Axiom" in src


def test_every_sema_axiom_has_a_validator(sema_axioms) -> None:
    unported, stale, stubs = set(), set(), set()
    for tn, (cls, ver, sema_nums) in sema_axioms.items():
        impl, has_stub = implemented_axioms(cls)
        if has_stub:
            stubs.add(f"{tn}/{ver}")
        for n in sema_nums:
            if n not in impl:
                unported.add(f"{tn}/{ver}:{n}")
        for n in impl:
            if n not in sema_nums:
                stale.add(f"{tn}/{ver}:{n}")
    assert not stubs, f"unported '# Implement Axiom' stubs: {sorted(stubs)}"
    assert unported == KNOWN_UNPORTED_AXIOMS, (
        f"new unported: {sorted(unported - KNOWN_UNPORTED_AXIOMS)}; "
        f"fixed (remove from allowlist): {sorted(KNOWN_UNPORTED_AXIOMS - unported)}"
    )
    assert stale == KNOWN_STALE_VALIDATORS, (
        f"new stale: {sorted(stale - KNOWN_STALE_VALIDATORS)}; "
        f"fixed (remove from allowlist): {sorted(KNOWN_STALE_VALIDATORS - stale)}"
    )


def axiom_test_names() -> set[str]:
    names: set[str] = set()
    for f in TESTS_DIR.glob("test_*.py"):
        names.update(re.findall(r"^def (test_\w+)\(", f.read_text(), re.M))
    return names


def test_every_sema_axiom_has_a_rejecting_test(sema_axioms) -> None:
    names = axiom_test_names()
    untested = set()
    for tn, (_, ver, sema_nums) in sema_axioms.items():
        for n in sema_nums:
            pat = re.compile(rf"^test_{snake(tn)}_axiom_{n}(_[a-z]|$)")
            if not any(pat.match(name) for name in names):
                untested.add(f"{tn}/{ver}:{n}")
    assert untested == KNOWN_UNTESTED_AXIOMS, (
        f"new untested: {sorted(untested - KNOWN_UNTESTED_AXIOMS)}; "
        f"fixed (remove from allowlist): {sorted(KNOWN_UNTESTED_AXIOMS - untested)}"
    )
