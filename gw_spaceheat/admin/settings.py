import logging
from typing import Optional
from typing import Self

from gwproactor import AppSettings
from gwproactor.config import MQTTClient
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from gwsproto.data_classes.house_0_names import H0N


class AdminClientSettings(AppSettings):
    target_gnode: str = ""
    default_timeout_seconds: int = int(5*60)
    link: MQTTClient = MQTTClient()
    verbosity: int = logging.WARN
    paho_verbosity: Optional[int] = None
    show_clock: bool = False
    show_footer: bool = False
    model_config = SettingsConfigDict(
        env_prefix="GWADMIN_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate(self) -> Self:
        self.link.update_tls_paths(self.paths.certs_dir, H0N.admin)
        return self
