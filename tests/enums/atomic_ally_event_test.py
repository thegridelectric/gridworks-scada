
from gwsproto.enums import AtomicAllyEvent


def test_aa_buffer_only_event() -> None:
    assert set(AtomicAllyEvent.values()) == {
        "NoMoreElec",
        "ElecBufferFull",
        "ElecBufferEmpty",
        "NoElecBufferFull",
        "NoElecBufferEmpty",
        "WakeUp",
        "GoDormant",
        "StartHackOil",
        "StopHackOil",
    }

    assert AtomicAllyEvent.default() == AtomicAllyEvent.GoDormant
    assert AtomicAllyEvent.enum_name() == "atomic.ally.event"
    assert AtomicAllyEvent.enum_version() == "000"
