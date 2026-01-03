import copy
import re
from functools import cached_property
from typing import Annotated, Optional

import yarl
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gwsproto.enums import TelemetryName, Unit
from gwsproto.named_types.hubitat_component_gt import HubitatRESTResolutionSettings
from gwsproto.named_types.rest_poller_gt import (
    DEFAULT_REST_POLL_PERIOD_SECONDS,
    RequestArgs,
    RESTPollerSettings,
    URLArgs,
    URLConfig,
)
from gwproto.utils import snake_to_camel

HUBITAT_ID_REGEX = re.compile(
    r".*/apps/api/(?P<api_id>-?\d+)/devices/(?P<device_id>-?\d+).*?"
)
HUBITAT_ACCESS_TOKEN_REGEX = re.compile(
    r".*\?.*access_token=(?P<access_token>[a-fA-F0-9\-]+).*"
)


class FibaroTempSensorSettingsGt(BaseModel):
    stack_depth: Annotated[int, Field(ge=1)]
    device_id: int
    fibaro_component_id: str
    analog_input_id: Annotated[int, Field(ge=1, le=2)]
    tank_label: str = ""
    exponent: int = 1
    telemetry_name: TelemetryName = TelemetryName.WaterTempCTimes1000
    temp_unit: Unit = Unit.Celcius
    enabled: bool = True
    web_listen_enabled: bool = True
    poll_period_seconds: Optional[float] = None
    """The actual poll_seconds_used will be the first of:
    1. Any value specified in an explicit 'rest' member, if 'rest' member is not None.
    2. The value from this object, if that value is not None.
    3. The value of HubitatTanksSettingsGt.default_poll_period_seconds if it is not None.
    4. The default value.
    """
    rest: Optional[RESTPollerSettings] = None
    model_config = ConfigDict(
        extra="allow",
        use_enum_values=True,
        alias_generator=snake_to_camel,
        populate_by_name=True,
    )


DEFAULT_SENSOR_NODE_NAME_FORMAT = "{tank_name}-depth{stack_depth}"


class FibaroTempSensorSettings(FibaroTempSensorSettingsGt):
    node_name: str
    model_config = ConfigDict(ignored_types=(cached_property, TelemetryName))

    @field_validator("rest")
    @classmethod
    def _collapse_rest_url(
        cls, v: Optional[RESTPollerSettings]
    ) -> Optional[RESTPollerSettings]:
        if v is not None:
            # Collapse session.base_url and request.url into
            # request.url.
            collapsed_url = v.url
            v.session.base_url = URLConfig()
            if v.request.url is None:
                v.request.url = URLConfig()
            v.request.url.url_args = URLArgs.from_url(collapsed_url)
        return v

    @cached_property
    def url(self) -> yarl.URL:
        if self.rest is None:
            raise ValueError("Cannot produce url since self.rest is None")
        return self.rest.url

    @cached_property
    def api_id(self) -> int:
        match = HUBITAT_ID_REGEX.match(str(self.url))
        if match is None:
            raise ValueError(
                f"url <{self.url}> does not match regex {HUBITAT_ID_REGEX}"
            )
        return int(match.group("api_id"))

    @property
    def host(self) -> str:
        if self.rest is None:
            raise ValueError("Cannot produce host since self.rest is None")
        host = self.rest.url.host
        if host is None:
            raise ValueError(f"Url {self.rest.url} has host None")
        return host

    @cached_property
    def access_token(self) -> Optional[str]:
        match = HUBITAT_ACCESS_TOKEN_REGEX.match(str(self.url))
        if match:
            return match.group("access_token")
        return None

    def clear_property_cache(self) -> None:
        if self.rest is not None:
            self.rest.clear_property_cache()
        for prop in [
            "url",
            "api_id",
            "access_token",
        ]:
            self.__dict__.pop(prop, None)

    def resolve_rest(  # noqa: C901, PLR0912
        self,
        hubitat: HubitatRESTResolutionSettings,
    ) -> None:
        # Constuct url config on top of maker api url url config
        constructed_config = copy.deepcopy(hubitat.maker_api_url_config)
        constructed_config.url_path_format += "/devices/{device_id}/refresh"
        if constructed_config.url_path_args is None:
            constructed_config.url_path_args = {}
        constructed_config.url_path_args["device_id"] = self.device_id

        if self.rest is None:
            # Since no "inline" rest configuration is present, use constructed url config
            if self.poll_period_seconds is None:
                poll_period_seconds = DEFAULT_REST_POLL_PERIOD_SECONDS
            else:
                poll_period_seconds = self.poll_period_seconds
            self.rest = RESTPollerSettings(
                poll_period_seconds=poll_period_seconds,
                request=RequestArgs(url=constructed_config),
            )
        elif self.rest.request.url is None:
            self.rest.request.url = constructed_config
        else:
            # An inline config exists; take items *not* in inline config from
            # constructed config (inline config 'wins' on disagreement)
            existing_config = self.rest.request.url
            if existing_config.url_args is None:
                existing_config.url_args = constructed_config.url_args
            else:
                if (
                    not existing_config.url_args.host
                    and constructed_config.url_args is not None
                ):
                    existing_config.url_args.host = constructed_config.url_args.host
                if existing_config.url_path_args is None:
                    existing_config.url_path_args = constructed_config.url_path_args
                else:
                    existing_config.url_path_args = dict(
                        constructed_config.url_path_args,
                        **existing_config.url_path_args,
                    )
        self.rest.clear_property_cache()

        # Verify new URL produced by combining any inline REST configuration
        # with hubitat configuration is valid.
        url_str = str(self.rest.url)
        hubitat_gt = hubitat.component_gt.Hubitat
        # check host
        if hubitat_gt.Host != self.rest.url.host:
            raise ValueError(
                "ERROR host expected to be "
                f"{hubitat_gt.Host} but host in url is "
                f"{self.rest.url.host}, from url: <{url_str}>"
            )

        # check api_id
        if hubitat_gt.MakerApiId != self.api_id:
            raise ValueError(
                "ERROR api_id expected to be "
                f"{hubitat_gt.MakerApiId} but api_id in url is "
                f"{self.api_id}, from url: <{url_str}>"
            )

        # check device_id
        id_match = HUBITAT_ID_REGEX.match(url_str)
        if not id_match:
            raise ValueError(
                f"ERROR. ID regex <{HUBITAT_ID_REGEX.pattern}> failed to match "
                f" url <{url_str}>"
            )
        found_device_id = int(id_match.group("device_id"))
        if self.device_id != found_device_id:
            raise ValueError(
                "ERROR explicit device_id is "
                f"{self.device_id} but device in url is "
                f"{found_device_id}, from url: <{url_str}>"
            )

        # check token match
        if hubitat_gt.AccessToken != self.access_token:
            raise ValueError(
                "ERROR explicit access_token is "
                f"{hubitat_gt.AccessToken} but device in url is "
                f"{self.access_token}, from url: <{url_str}>"
            )

    @classmethod
    def create(
        cls,
        tank_name: str,
        settings_gt: FibaroTempSensorSettingsGt,
        hubitat: HubitatRESTResolutionSettings,
        default_poll_period_seconds: Optional[float] = None,
        node_name_format: str = DEFAULT_SENSOR_NODE_NAME_FORMAT,
    ) -> "FibaroTempSensorSettings":
        settings = FibaroTempSensorSettings(
            node_name=node_name_format.format(
                tank_name=tank_name,
                stack_depth=settings_gt.stack_depth,
            ),
            **settings_gt.model_dump(),
        )
        if settings.poll_period_seconds is None:
            settings.poll_period_seconds = default_poll_period_seconds
        settings.resolve_rest(hubitat)
        return settings


DEFAULT_TANK_MODULE_VOLTAGE = 23.7


class HubitatTankSettingsGt(BaseModel):
    hubitat_component_id: str
    sensor_supply_voltage: float = DEFAULT_TANK_MODULE_VOLTAGE
    default_poll_period_seconds: Optional[float] = None
    devices: list[FibaroTempSensorSettingsGt] = []
    web_listen_enabled: bool = True
    model_config = ConfigDict(
        extra="allow", alias_generator=snake_to_camel, populate_by_name=True
    )
