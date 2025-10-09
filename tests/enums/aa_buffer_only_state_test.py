
from gwsproto.enums import AaBufferOnlyState


def test_aa_buffer_only_event() -> None:
    assert set(AaBufferOnlyState.values()) == {
        "Initializing",
        "HpOn",
        "HpOff",
        "HpOffOilBoilerTankAquastat",
        "Dormant",
    }

    assert AaBufferOnlyState.default() == AaBufferOnlyState.Dormant
    assert AaBufferOnlyState.enum_name() == "aa.buffer.only.state"
    assert AaBufferOnlyState.enum_version() == "000"
