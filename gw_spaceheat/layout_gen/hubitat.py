from gwsproto.enums import ActorClass
from gwsproto.enums import Gw1DeviceType
from gwsproto.named_types import ComponentAttributeClassGt
from gwsproto.named_types import HubitatComponentGt
from gwsproto.named_types import SpaceheatNodeGt
from gwsproto.named_types.hubitat_gt import HubitatGt

from layout_gen.layout_db import LayoutDb
from gwsproto.data_classes.house_0_names import H0N

def add_hubitat(
    db: LayoutDb,
    hubitat: HubitatGt,
) -> str:
    if not db.has_device_type_record(Gw1DeviceType.HubitatC7Hub):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    DeviceType=Gw1DeviceType.HubitatC7Hub,
                    DisplayName="Hubitat Elevation C-7",
                ),
            ]
        )
    hubitat_component_alias = f"Hubitat {hubitat.MacAddress[-8:]}"
    if not db.component_id_by_alias(hubitat_component_alias):
        db.add_components(
            [
                HubitatComponentGt(
                    ComponentId=db.make_component_id(hubitat_component_alias),
                    DeviceType=Gw1DeviceType.HubitatC7Hub,
                    DisplayName=hubitat_component_alias,
                    Hubitat=hubitat,
                    HwUid=hubitat.MacAddress[-8:].replace(":", "").lower(),
                    ConfigList=[],
                )
            ]
        )
        db.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(H0N.hubitat),
                    Name=H0N.hubitat,
                    ActorHierarchyName=f"{H0N.primary_scada}.{H0N.hubitat}",
                    ActorClass=ActorClass.Hubitat,
                    DisplayName=hubitat_component_alias,
                    ComponentId=db.component_id_by_alias(hubitat_component_alias),
                )
            ]
        )
    return hubitat_component_alias
