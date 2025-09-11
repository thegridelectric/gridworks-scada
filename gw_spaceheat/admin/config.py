import logging
from pathlib import Path
from typing import Any
from typing import Optional

from gwproactor.config import MQTTClient
from gwproactor.config import Paths
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

class ScadaConfig(BaseSettings):
    mqtt: MQTTClient = MQTTClient()
    long_name: str = ""

class AdminConfig(BaseModel):
    scadas: dict[str, ScadaConfig] = {}
    default_scada: str = ""
    use_last_scada: bool = False
    verbosity: int = logging.WARN
    paho_verbosity: Optional[int] = None
    show_clock: bool = False
    show_footer: bool = False
    default_timeout_seconds: int = int(5*60)

class AdminPaths(Paths):

    @property
    def admin_config_path(self) -> Path:
        return Path(self.config_dir) / "admin-config.json"

    @property
    def last_scada_path(self) -> Path:
        return Path(self.config_dir) / "last-scada.txt"

    def duplicate(
        self,
        **kwargs: Any,
    ) -> "AdminPaths":
        return AdminPaths(**super().duplicate(**kwargs).model_dump())

class AdminSettings(BaseSettings):
    config_name: str = "admin"

    model_config = SettingsConfigDict(
        env_prefix="GWADMIN_",
        env_nested_delimiter="__",
        extra="ignore",
    )

class CurrentAdminConfig(BaseModel):
    paths: AdminPaths = AdminPaths()
    config: AdminConfig = AdminConfig()
    curr_scada: str = ""

    def save_curr_scada(self, scada: str) -> None:
        with self.paths.last_scada_path.open(mode="w") as file:
            file.write(scada)

    def save_config(self) -> None:
        with self.paths.admin_config_path.open(mode="w") as file:
            file.write(self.config.model_dump_json(indent=2))

    def add_scada(self, short_name: str, long_name: str, mqtt_client_config: MQTTClient) -> Optional[ScadaConfig]:
        if short_name not in self.config.scadas:
            self.config.scadas[short_name] = ScadaConfig(
                long_name=long_name,
                mqtt=mqtt_client_config,
            )
            self.config.scadas[short_name].mqtt.update_tls_paths(self.paths.certs_dir, short_name)
            return self.config.scadas[short_name]
        return None

    def last_scada(self) -> str:
        if self.paths.last_scada_path.exists():
            return self.paths.last_scada_path.read_text()
        return ""