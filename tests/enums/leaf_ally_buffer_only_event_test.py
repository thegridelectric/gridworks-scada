
from gwsproto.enums import LeafAllyBufferOnlyEvent


def test_leaf_ally_buffer_only_event() -> None:
    assert set( LeafAllyBufferOnlyEvent.values()) == {
        "GoDormant",
        "WakeUp",
        "NoMoreElec",
        "BufferFull",
        "ChargeBuffer",
        "StartNonElectricBackup",
        "StopNonElectricBackup",
    }

    assert  LeafAllyBufferOnlyEvent.default() ==  LeafAllyBufferOnlyEvent.GoDormant
    assert  LeafAllyBufferOnlyEvent.enum_name() == "gw1.leaf.ally.buffer.only.event"
    assert  LeafAllyBufferOnlyEvent.enum_version() == "000"
