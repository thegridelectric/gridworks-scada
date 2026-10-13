"""Tests gw1.zone.thermostat type, version 000"""


from gwsproto.named_types import ZoneThermostat
from tests.named_types.sema_oracle import assert_refused


def base_thermostat() -> dict:
    return {
        "Kind": "HoneywellViaHubitat",
        "ComponentId": "8c1ff8a4-8b3b-4c1f-9c11-f37afd0e2c6a",
        "TypeName": "gw1.zone.thermostat",
        "Version": "000",
    }


def test_zone_thermostat_generated() -> None:
    d = base_thermostat()

    d2 = ZoneThermostat.model_validate(d).model_dump(by_alias=True, exclude_none=True)

    assert d2 == d


def test_zone_thermostat_axiom_1() -> None:
    d = base_thermostat()
    d["Kind"] = "MechanicalDial"

    assert_refused(ZoneThermostat, d, match="Axiom 1 \\(NoComponentOnDumbStat\\) failed")
