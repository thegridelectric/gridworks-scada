import logging
from typing import Optional
from typing import Self

from gwproactor import AppSettings
from gwproactor.config import MQTTClient
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from data_classes.house_0_names import H0N


class WebInterSettings(AppSettings):
    target_gnode: str = ""
    web_port: int = 8080
    web_host: str = "localhost"
    link: MQTTClient = MQTTClient()
    verbosity: int = logging.WARN
    paho_verbosity: Optional[int] = None
    model_config = SettingsConfigDict(
        env_prefix="GWWEBINTER_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate(self) -> Self:
        # Force TLS to be disabled for web interface
        self.link.tls.use_tls = False
        print(f"DEBUG: Forced TLS use_tls = {self.link.tls.use_tls}")
        print(f"DEBUG: MQTT host = {self.link.host}")
        print(f"DEBUG: MQTT port = {self.link.port}")
        print(f"DEBUG: MQTT username = {self.link.username}")
        return self
