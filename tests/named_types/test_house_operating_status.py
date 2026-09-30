"""gw.house.operating.status round-trips, and its two axioms reject."""

import pytest

from gwsproto.named_types import HouseOperatingStatus

STATUS = {
    "ScadaAlias": "d1.isone.me.versant.keene.beech.scada",
    "ValidationState": "ValidatedRealAssetAndGps",
    "Standby": False,
    "StandbyPosture": "NoHeatingOrCooling",
    "SeasonalStorageMode": "AllTanks",
    "ServiceMode": "Heating",
    "AcceptsDispatch": True,
    "TopState": "Auto",
    "LtnDispatching": False,
    "UnixMs": 1728651445746,
    "TypeName": "gw.house.operating.status",
    "Version": "000",
}


def test_gw_house_operating_status_generated() -> None:
    d2 = HouseOperatingStatus.model_validate(STATUS).model_dump(exclude_none=True)
    assert d2 == STATUS
    refusing = dict(STATUS, AcceptsDispatch=False, DispatchRefusalReason="NoAggregator")
    assert HouseOperatingStatus.model_validate(refusing).model_dump(exclude_none=True) == refusing


def test_gw_house_operating_status_axiom_1_refusal_reason_presence() -> None:
    with pytest.raises(ValueError, match="Axiom 1 \\(RefusalReasonPresence\\)"):
        HouseOperatingStatus.model_validate(dict(STATUS, AcceptsDispatch=False))
    with pytest.raises(ValueError, match="Axiom 1 \\(RefusalReasonPresence\\)"):
        HouseOperatingStatus.model_validate(dict(STATUS, DispatchRefusalReason="NoAggregator"))


def test_gw_house_operating_status_axiom_2_standby_refuses_dispatch() -> None:
    with pytest.raises(ValueError, match="Axiom 2 \\(StandbyRefusesDispatch\\)"):
        HouseOperatingStatus.model_validate(dict(STATUS, Standby=True))
    with pytest.raises(ValueError, match="Axiom 2 \\(StandbyRefusesDispatch\\)"):
        HouseOperatingStatus.model_validate(
            dict(STATUS, Standby=True, AcceptsDispatch=False, DispatchRefusalReason="NoAggregator")
        )
    HouseOperatingStatus.model_validate(
        dict(STATUS, Standby=True, AcceptsDispatch=False, DispatchRefusalReason="Standby")
    )
