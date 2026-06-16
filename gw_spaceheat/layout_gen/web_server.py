from gwsproto.enums import DeviceType
from gwproto.type_helpers import WebServerGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt

from layout_gen import LayoutDb

def add_web_server(
    db: LayoutDb,
    web_server: WebServerGt
) -> WebServerComponentGt:
    component_alias = f"Web Server {web_server.Name}"
    if not db.component_id_by_alias(component_alias):
        db.add_components(
            [
                WebServerComponentGt(
                    ComponentId=db.make_component_id(component_alias),
                    DeviceType=DeviceType.AbstractWebServer,
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
