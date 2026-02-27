
from gwsproto.enums import LeafAllyBufferOnlyState


def test_leaf_ally_buffer_only_event() -> None:
    assert set(LeafAllyBufferOnlyState.values()) == {
        "Initializing",
        "HpOn",
        "HpOff",
        "HpOffNonElectricBackup",
        "Dormant",
    }

    assert LeafAllyBufferOnlyState.default() == LeafAllyBufferOnlyState.Dormant
    assert LeafAllyBufferOnlyState.enum_name() == "gw1.leaf.ally.buffer.only.state"
    assert LeafAllyBufferOnlyState.enum_version() == "000"
