
from gwsproto.enums import AtomicAllyState


def test_aa_buffer_only_event() -> None:
    assert set(AtomicAllyState.values()) == {
        "Dormant",
        "Initializing",
        "HpOnStoreOff",
        "HpOnStoreCharge",
        "HpOffStoreOff",
        "HpOffStoreDischarge",
        "HpOffOilBoilerTankAquastat",
    }

    assert AtomicAllyState.default() == AtomicAllyState.Dormant
    assert AtomicAllyState.enum_name() == "atomic.ally.state"
    assert AtomicAllyState.enum_version() == "000"
