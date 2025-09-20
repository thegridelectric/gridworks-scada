"""Tests snapshot.spaceheat type, version 003"""

from gwsproto.named_types import SnapshotSpaceheat


def test_snapshot_spaceheat_generated() -> None:
    d = {
        "FromGNodeAlias": "d1.isone.ct.newhaven.rose.scada",
        "FromGNodeInstanceId": "0384ef21-648b-4455-b917-58a1172d7fc1",
        "SnapshotTimeUnixMs": 1709915800472,
        "LatestReadingList": [],
        "LatestStateList": [
            {
                "MachineHandle": "auto.pico-cycler",
                "StateEnum": "pico.cycler.state",
                "State": "PicosLive",
                "UnixMs": 1731168353695,
                "Cause": "ConfirmRebooted",
                "TypeName": "single.machine.state",
                "Version": "000",
            }
    ],
        "TypeName": "snapshot.spaceheat",
        "Version": "003",
    }

    d2 = SnapshotSpaceheat.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
