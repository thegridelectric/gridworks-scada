"""The LTN reads the store's tank count off the layout.lite it receives."""
from gwsproto.data_classes.layout_lite_dc import LayoutLiteDc
from gwsproto.named_types import LayoutLite, TouTariff


TARIFF = {
    "TypeName": "gw.tou.tariff",
    "Version": "000",
    "Alias": "versant.a1.home.eco.bonus",
    "DisplayName": "Home Eco Rate with Bonus Meter",
    "TimezoneStr": "America/New_York",
    "OnPeakWindows": [
        {
            "TypeName": "gw.tou.window",
            "Version": "000",
            "Start": "07:00",
            "End": "12:00",
            "Days": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday"
            ]
        },
        {
            "TypeName": "gw.tou.window",
            "Version": "000",
            "Start": "16:00",
            "End": "20:00",
            "Days": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday"
            ]
        }
    ]
}


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
        Tariff=TouTariff.model_validate(TARIFF),
    )
    assert LayoutLiteDc(gt).total_store_tanks == 2
    assert LayoutLiteDc(gt.model_copy(update={"ShNodes": [gt.ShNodes[0]]})).total_store_tanks == 0
