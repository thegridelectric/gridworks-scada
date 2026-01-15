
from gwsproto.enums import LeafAllyAllTanksState


def test_leaf_ally_all_tanks_state() -> None:
    assert set(LeafAllyAllTanksState.values()) == {
        "Dormant",
        "Initializing",
        "HpOnStoreOff",
        "HpOnStoreCharge",
        "HpOffStoreOff",
        "HpOffStoreDischarge",
        "HpOffNonElectricBackup",
    }

    assert  LeafAllyAllTanksState.default() ==  LeafAllyAllTanksState.Dormant
    assert  LeafAllyAllTanksState.enum_name() == "gw1.leaf.ally.all.tanks.state"
    assert  LeafAllyAllTanksState.enum_version() == "000"
