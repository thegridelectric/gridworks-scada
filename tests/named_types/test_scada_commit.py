"""gw.scada.commit round-trips."""

from gwsproto.named_types import ScadaCommit

COMMIT = {
    "ScadaAlias": "d1.isone.me.versant.keene.beech.scada",
    "GitCommit": "109d44041c2b3d4e5f60718293a4b5c6d7e8f901",
    "MessageCreatedMs": 1728651445746,
    "TypeName": "gw.scada.commit",
    "Version": "000",
}


def test_gw_scada_commit_generated() -> None:
    assert ScadaCommit.model_validate(COMMIT).model_dump(exclude_none=True) == COMMIT
    dirty = dict(COMMIT, GitCommit=COMMIT["GitCommit"] + "-dirty")
    assert ScadaCommit.model_validate(dirty).model_dump(exclude_none=True) == dirty
