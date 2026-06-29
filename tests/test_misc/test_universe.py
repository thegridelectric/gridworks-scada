import pytest

from universe import (
    UniverseMismatchError,
    assert_universe_coherence,
    universe_of_alias,
    universe_of_host,
)


def test_universe_of_alias():
    assert universe_of_alias("hw1.isone.me.versant.keene.maple.scada") == "hw1"
    assert universe_of_alias("d1.isone.ct.newhaven.orange1.scada") == "d1"
    assert universe_of_alias("w1.isone.x") == "w1"


def test_universe_of_host():
    assert universe_of_host("hw1-1.electricity.works") == "hw1"
    assert universe_of_host("d1-2.electricity.works") == "d1"
    # the dev rabbit serves the d1 universe on localhost
    assert universe_of_host("localhost") == "d1"
    assert universe_of_host("127.0.0.1") == "d1"


def test_coherent_passes():
    # d1 aliases on the localhost (d1) dev rabbit
    assert_universe_coherence(
        {"scada": "d1.x.scada", "ltn": "d1.x", "terminal_asset": "d1.x.ta"},
        "localhost",
    )
    # hw1 aliases on the hw1 broker
    assert_universe_coherence(
        {"scada": "hw1.x.scada"}, "hw1-1.electricity.works"
    )


def test_mismatch_raises():
    # a d1 scada pointed at the hw1 broker — the thing the guardrail exists to stop
    with pytest.raises(UniverseMismatchError):
        assert_universe_coherence(
            {"scada": "d1.x.scada"}, "hw1-1.electricity.works"
        )
    # an hw1 layout on the localhost dev rabbit (d1)
    with pytest.raises(UniverseMismatchError):
        assert_universe_coherence({"scada": "hw1.x.scada"}, "localhost")
