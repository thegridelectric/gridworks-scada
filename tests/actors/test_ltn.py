"""The LTN's FLO call: one `flo.params` to bruce's boundary and one
`flo.recommendation` back, as the child process runs it, with bruce
installed in the venv (`tools/mkenv.sh`). The store is the one-tank,
nine-sensor, 120-gallon shape whose transition matrix bruce's own tests
cache, so the run takes seconds."""

import pytest

from actors.ltn.ltn import BRUCE_FLO_AVAILABLE, _flo_worker
from gwsproto.enums import SeasonalStorageMode
from gwsproto.named_types import FloRecommendation, WaterStore
from tests.actors.test_flo_request import build


class Answer:
    """Stands in for the child's result queue."""

    def __init__(self) -> None:
        self.results = []

    def put(self, result) -> None:
        self.results.append(result)


@pytest.mark.skipif(not BRUCE_FLO_AVAILABLE, reason="bruce is not installed in this venv")
def test_the_flo_answers_the_request_with_a_recommendation() -> None:
    params = build(
        horizon_hours=6,
        water_store=WaterStore(TotalStoreTanks=1, GallonsPerTank=120, TempSensorsPerTank=9),
        storage_mode=SeasonalStorageMode.BufferOnly,
    )
    answer = Answer()
    _flo_worker(params.model_dump_json(by_alias=True).encode("utf-8"), answer)
    (status, payload), = answer.results
    assert status == "ok", payload
    recommendation = FloRecommendation.model_validate_json(payload)
    assert recommendation.BidderAlias == params.GNodeAlias
    assert len(recommendation.PqPairs) == len(recommendation.OptimalPathList) >= 1
    assert recommendation.PqPairs[0].PriceX1000 == round(params.PriceMaxUsdMwh * 1000)
    for pair, path in zip(recommendation.PqPairs, recommendation.OptimalPathList, strict=True):
        assert path.StartUnixS == params.StartUnixS
        assert pair.QuantityX1000 == path.HpAvgWList[0]


def test_without_bruce_the_worker_answers_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import actors.ltn.ltn as ltn_module

    monkeypatch.setattr(ltn_module, "BRUCE_FLO_AVAILABLE", False)
    answer = Answer()
    _flo_worker(b"{}", answer)
    assert answer.results[0][0] == "error"
