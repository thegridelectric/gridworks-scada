from gwsproto.enums import MakeModel
from gwproto.type_helpers import WebServerGt
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt

from layout_gen import LayoutDb

def add_web_server(
    db: LayoutDb,
    web_server: WebServerGt
) -> WebServerComponentGt:
    cac_display_name = "Web Server CAC"
    if not db.cac_id_by_alias(cac_display_name):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=db.make_cac_id(
                        make_model=MakeModel.UNKNOWNMAKE__UNKNOWNMODEL,
                        cac_alias=cac_display_name
                    ),
                    DisplayName=cac_display_name,
                    MakeModel=MakeModel.UNKNOWNMAKE__UNKNOWNMODEL,
                ),
            ]
        )
    cac_id = db.cac_id_by_alias(cac_display_name)
    if cac_id is None:
        raise Exception("That's strange, should have made a cac id")
    component_alias = f"Web Server {web_server.Name}"
    if not db.component_id_by_alias(component_alias):
        db.add_components(
            [
                WebServerComponentGt(
                    ComponentId=db.make_component_id(component_alias),
                    ComponentAttributeClassId=cac_id,
                    DisplayName=component_alias,
                    WebServer=web_server,
                    ConfigList=[]
                ),
            ]
        )
    component_id = db.component_id_by_alias(component_alias)
    if component_id is None:
        raise Exception("That's strange, should have made a component id")
    web_server_component_gt = db.components_by_id[component_id]
    assert isinstance(web_server_component_gt, WebServerComponentGt)
    return web_server_component_gt
