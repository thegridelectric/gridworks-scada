
from gwsproto.enums import AaBufferOnlyEvent


def test_aa_buffer_only_event() -> None:
    assert set(AaBufferOnlyEvent.values()) == {
        "NoMoreElec",
        "BufferFull",
        "ChargeBuffer",
        "StartHackOil",
        "StopHackOil",
        "GoDormant",
        "WakeUp",
    }

    assert AaBufferOnlyEvent.default() == AaBufferOnlyEvent.GoDormant
    assert AaBufferOnlyEvent.enum_name() == "aa.buffer.only.event"
    assert AaBufferOnlyEvent.enum_version() == "000"
