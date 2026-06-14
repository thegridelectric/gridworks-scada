from typing import Literal, Optional

import yarl
from pydantic_extra_types.mac_address import MacAddress

from gwsproto.named_types.component_gt import ComponentGt
from gwsproto.named_types.hubitat_gt import HubitatGt
from gwsproto.named_types.rest_poller_gt import URLConfig


class HubitatComponentGt(ComponentGt):
    """
    A Hubitat hub component instance.

    Sema word: ``hubitat.component.gt`` (flat shell carrying ``DeviceType`` + ``Hubitat``).
    The MakerAPI URL helpers below (``url_config`` / ``maker_api_url_config`` / ``urls`` /
    ``refresh_url`` …) are NOT part of the sema contract and will NOT be generated from
    sema in the proactor port — they delegate to HubitatGt and must remain in app code.
    See HubitatGt; this serves the five legacy House0 production homes with no forward
    expansion.
    """

    Hubitat: HubitatGt
    TypeName: Literal["hubitat.component.gt"] = "hubitat.component.gt"

    def url_config(self) -> URLConfig:
        return self.Hubitat.url_config()

    def maker_api_url_config(self) -> URLConfig:
        return self.Hubitat.maker_api_url_config()

    def urls(self) -> dict[str, Optional[yarl.URL]]:
        return self.Hubitat.urls()

    def refresh_url_config(self, device_id: int) -> URLConfig:
        return self.Hubitat.refresh_url_config(device_id)

    def refresh_url(self, device_id: int) -> yarl.URL:
        return self.Hubitat.refresh_url(device_id)

    @classmethod
    def make_stub(cls, component_id: str) -> "HubitatComponentGt":
        return HubitatComponentGt(
            ComponentId=component_id,
            DeviceType="HubitatC7Hub",
            Hubitat=HubitatGt(
                Host="",
                MakerApiId=-1,
                AccessToken="",
                MacAddress=MacAddress("00:00:00:00:00:00"),
            ),
            ConfigList=[],
        )


class HubitatRESTResolutionSettings:
    component_gt: HubitatComponentGt
    maker_api_url_config: URLConfig

    def __init__(self, component_gt: HubitatComponentGt) -> None:
        self.component_gt = component_gt
        self.maker_api_url_config = self.component_gt.maker_api_url_config()
