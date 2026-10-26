"""The LTN takes its operational parameters from its own settings and its
own hardware layout; layout.lite carries none of them."""

import json

from actors.ltn.config import LtnSettings
from gwsproto.data_classes.layout_lite_dc import LayoutLiteDc
from gwsproto.named_types import Ha1Params, LayoutLite


HA1 = {
    "AlphaTimes10": 120, "BetaTimes100": -22, "GammaEx6": 0,
    "IntermediatePowerKw": 1.5, "IntermediateRswtF": 100, "DdPowerKw": 12,
    "DdRswtF": 160, "DdDeltaTF": 20, "HpMaxKwEl": 6.0, "MaxEwtF": 170,
    "LoadOverestimationPercent": 10, "CopIntercept": 1.02, "CopOatCoeff": 0.0257,
    "CopLwtCoeff": 0.0, "CopMin": 1.4, "CopMinOatF": 15.0, "HpTurnOnMinutes": 12,
    "TypeName": "ha1.params", "Version": "006",
}


def test_ltn_settings_default_to_no_ha1_params(monkeypatch) -> None:
    monkeypatch.delenv("LTN_HA1_PARAMS", raising=False)
    monkeypatch.delenv("LTN_KEEP_BUFFER_FULL", raising=False)
    settings = LtnSettings(_env_file=None)
    assert settings.ha1_params is None
    assert settings.keep_buffer_full is False


def test_ltn_settings_read_ha1_params_and_keep_buffer_full(monkeypatch) -> None:
    monkeypatch.setenv("LTN_HA1_PARAMS", json.dumps(HA1))
    monkeypatch.setenv("LTN_KEEP_BUFFER_FULL", "true")
    settings = LtnSettings(_env_file=None)
    assert settings.ha1_params == Ha1Params(**HA1)
    assert settings.keep_buffer_full is True


def node(name: str, actor_class: str) -> dict:
    return {
        "ActorClass": actor_class,
        "ActorHierarchyName": "s" if name == "s" else f"s.{name}",
        "DisplayName": name,
        "Name": name,
        "ShNodeId": f"00000000-0000-4000-8000-00000000000{len(name)}",
        "TypeName": "spaceheat.node.gt",
        "Version": "303",
    }


def test_layout_lite_dc_counts_store_tanks_from_sh_nodes() -> None:
    gt = LayoutLite(
        FromGNodeAlias="hw1.isone.me.versant.keene.beech.scada",
        CreatedMs=1728651445746,
        MessageId="1302c0f8-1983-43b2-90d2-61678d731db3",
        HardwareLayoutTypeName="gw.house0.layout",
        ZoneList=[],
        CriticalZoneList=[],
        ShNodes=[
            node("s", "PrimaryScada"),
            node("tank1", "ApiTankModule"),
            node("tank2", "ApiTankModule"),
        ],
        DataChannels=[],
        DerivedChannels=[],
        StateMachines=[],
    )
    assert LayoutLiteDc(gt).total_store_tanks == 2
    assert LayoutLiteDc(gt.model_copy(update={"ShNodes": [gt.ShNodes[0]]})).total_store_tanks == 0
