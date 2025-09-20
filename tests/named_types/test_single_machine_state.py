"""Tests single.machine.state type, version 000"""

from gwsproto.named_types import SingleMachineState


def test_single_machine_state_generated() -> None:
    d = {
        "MachineHandle": "auto.pico-cycler",
        "StateEnum": "pico.cycler.state",
        "State": "PicosLive",
        "UnixMs": 1731168353695,
        "Cause": "ConfirmRebooted",
        "TypeName": "single.machine.state",
        "Version": "000",
    }

    d2 = SingleMachineState.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
