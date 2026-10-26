"""gw.house.operating.status round-trips, and its two axioms reject."""


from gwsproto.named_types import HouseOperatingStatus
from tests.named_types.sema_oracle import assert_refused

STATUS = {
    "ScadaAlias": "d1.isone.me.versant.keene.beech.scada",
    "ValidationState": "ValidatedRealAssetAndGps",
    "Standby": False,
    "StandbyPosture": "NoHeatingOrCooling",
    "SeasonalStorageMode": "AllTanks",
    "ServiceMode": "Heating",
    "AcceptsDispatch": True,
    "TopState": "Auto",
    "ScadaBlind": False,
    "LtnDispatching": False,
    "CreatedMs": 1728651445746,
    "TypeName": "gw.house.operating.status",
    "Version": "000",
}


def test_gw_house_operating_status_generated() -> None:
    d2 = HouseOperatingStatus.model_validate(STATUS).model_dump(exclude_none=True)
    assert d2 == STATUS
    refusing = dict(STATUS, AcceptsDispatch=False, DispatchRefusalReason="ScadaBlind")
    assert HouseOperatingStatus.model_validate(refusing).model_dump(exclude_none=True) == refusing


def test_gw_house_operating_status_axiom_1_refusal_reason_presence() -> None:
    assert_refused(HouseOperatingStatus, dict(STATUS, AcceptsDispatch=False), match="Axiom 1 \\(RefusalReasonPresence\\)")
    assert_refused(HouseOperatingStatus, dict(STATUS, DispatchRefusalReason="ScadaBlind"), match="Axiom 1 \\(RefusalReasonPresence\\)")


def test_gw_house_operating_status_axiom_2_standby_refuses_dispatch() -> None:
    assert_refused(HouseOperatingStatus, dict(STATUS, Standby=True), match="Axiom 2 \\(StandbyRefusesDispatch\\)")
    assert_refused(HouseOperatingStatus, dict(STATUS, Standby=True, AcceptsDispatch=False, DispatchRefusalReason="ScadaBlind"), match="Axiom 2 \\(StandbyRefusesDispatch\\)")
    HouseOperatingStatus.model_validate(
        dict(STATUS, Standby=True, AcceptsDispatch=False, DispatchRefusalReason="OperatorHold")
    )
