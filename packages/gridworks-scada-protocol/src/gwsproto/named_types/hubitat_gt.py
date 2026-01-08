import typing
from typing import Optional

import yarl
from pydantic import BaseModel, ConfigDict
from pydantic_extra_types.mac_address import MacAddress

from gwsproto.named_types.rest_poller_gt import URLArgs, URLConfig


class URLConfigWithUrlArgs(URLConfig):
    """
    A URLConfig with non-None url_args
    """

    url_args: URLArgs


class URLConfigForMakerAPI(URLConfigWithUrlArgs):
    """
    A URLConfig with non-None url_args and url_path_args suitable for creating
    a MakerAPI url.
    """

    url_path_args: dict[str, str | int | float]


class HubitatGt(BaseModel):
    Host: str
    MakerApiId: int
    AccessToken: str
    MacAddress: MacAddress
    WebListenEnabled: bool = True
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @property
    def listen_path(self) -> str:
        return self.MacAddress.replace(":", "-")

    def listen_url(self, url: yarl.URL) -> yarl.URL:
        return url / self.listen_path

    def url_config(self) -> URLConfigWithUrlArgs:
        return URLConfigWithUrlArgs(
            url_args=URLArgs(
                scheme="http",
                host=self.Host,
            ),
        )

    def maker_api_url_config(self) -> URLConfigForMakerAPI:
        config = self.url_config()
        if config.url_args is None:
            raise ValueError(
                f"ERROR. URLConfig.url_args ({config.url_args})"
                " are insufficient to create MakerAPI url"
            )
        if config.url_args.query is None:
            config.url_args.query = []
        config.url_args.query.append(("access_token", self.AccessToken))
        config.url_path_format += "/apps/api/{app_id}"
        if config.url_path_args is None:
            config.url_path_args = {}
        config.url_path_args.update({"app_id": self.MakerApiId})
        return typing.cast(URLConfigForMakerAPI, config)

    def devices_url_config(self) -> URLConfig:
        config = self.maker_api_url_config()
        config.url_path_format += "/devices"
        return config

    def url_configs(self) -> dict[str, URLConfig]:
        return {
            "base": self.url_config(),
            "maker_api": self.maker_api_url_config(),
            "devices": self.devices_url_config(),
        }

    def urls(self) -> dict[str, Optional[yarl.URL]]:
        return {
            name: URLConfig.make_url(config)
            for name, config in self.url_configs().items()
        }

    def refresh_url_config(self, device_id: int) -> URLConfig:
        config = self.maker_api_url_config()
        config.url_path_format += "/devices/{device_id}/refresh"  # noqa: RUF027
        config.url_path_args["device_id"] = device_id
        return config

    def refresh_url(self, device_id: int) -> yarl.URL:
        url = URLConfig.make_url(self.refresh_url_config(device_id))
        if url is None:
            raise ValueError(
                f"ERROR. refreshed URL could not produce URL from <{self}> "
                f"and device_id {device_id}"
            )
        return url
