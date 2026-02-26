
from gwsproto.enums import LeafAllyAllTanksEvent


def test_leaf_ally_buffer_only_event() -> None:
    assert set( LeafAllyAllTanksEvent.values()) == {
        "NoMoreElec",
        "ElecBufferFull",
        "ElecBufferEmpty",
        "NoElecBufferFull",
        "NoElecBufferEmpty",
        "WakeUp",
        "GoDormant",
        "StartNonElectricBackup",
        "StopNonElectricBackup",
        "DefrostDetected",
    }

    assert  LeafAllyAllTanksEvent.default() ==  LeafAllyAllTanksEvent.GoDormant
    assert  LeafAllyAllTanksEvent.enum_name() == "gw1.leaf.ally.all.tanks.event"
    assert  LeafAllyAllTanksEvent.enum_version() == "000"
