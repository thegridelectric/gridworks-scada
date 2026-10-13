"""Tests slow.dispatch.contract type, version 000"""


from gwsproto.named_types import SlowDispatchContract
from tests.named_types.sema_oracle import assert_refused

CONTRACT = {
    "ScadaAlias": "hw1.isone.me.versant.keene.beech.scada",
    "StartS": 1757300400,
    "DurationMinutes": 60,
    "AvgPowerWatts": 3000,
    "OilBoilerOn": False,
    "ContractId": "9d3b2a1c-8e7f-4a6b-b5c4-d3e2f1a0b9c8",
    "TypeName": "slow.dispatch.contract",
    "Version": "000",
}


def test_slow_dispatch_contract_generated() -> None:
    d2 = SlowDispatchContract.model_validate(CONTRACT).model_dump(by_alias=True)
    assert d2 == CONTRACT


def test_slow_dispatch_contract_axiom_1_start_off_five_minutes() -> None:
    assert_refused(SlowDispatchContract, dict(CONTRACT, StartS=CONTRACT["StartS"] + 60), match="Axiom 1 \\(StartOnFiveMinutes\\)")


def test_slow_dispatch_contract_axiom_2_oil_boiler_with_power() -> None:
    assert_refused(SlowDispatchContract, dict(CONTRACT, OilBoilerOn=True), match="Axiom 2 \\(OilBoilerDrawsNoPower\\)")
    SlowDispatchContract.model_validate(
        dict(CONTRACT, OilBoilerOn=True, AvgPowerWatts=0)
    )
