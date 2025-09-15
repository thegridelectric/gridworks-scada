import logging
import os
from pathlib import Path
from typing import Optional
from typing import Self

import dotenv
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

    def __init__(self, **kwargs):
        # Load .env file before initializing
        self._load_env_file()
        super().__init__(**kwargs)

    def _load_env_file(self):
        """Load .env file from current directory or project root"""
        # Try to find .env file
        current_dir = Path.cwd()
        env_file = current_dir / ".env"
        
        if not env_file.exists():
            # Try project root (go up directories looking for .env)
            for parent in current_dir.parents:
                potential_env = parent / ".env"
                if potential_env.exists():
                    env_file = potential_env
                    break
        
        if env_file.exists():
            print(f"DEBUG: Loading .env file from: {env_file}")
            dotenv.load_dotenv(env_file, override=True)
            
            # Debug: Check if environment variables are actually loaded
            print(f"DEBUG: After loading .env:")
            print(f"  GWWEBINTER__LINK__HOST: {os.getenv('GWWEBINTER__LINK__HOST')}")
            print(f"  GWWEBINTER__LINK__PORT: {os.getenv('GWWEBINTER__LINK__PORT')}")
            print(f"  GWWEBINTER__LINK__USERNAME: {os.getenv('GWWEBINTER__LINK__USERNAME')}")
        else:
            print("DEBUG: No .env file found")

    @model_validator(mode="after")
    def validate(self) -> Self:
        # Force TLS to be disabled for web interface
        self.link.tls.use_tls = False
        print(f"DEBUG: Forced TLS use_tls = {self.link.tls.use_tls}")
        print(f"DEBUG: MQTT host = {self.link.host}")
        print(f"DEBUG: MQTT port = {self.link.port}")
        print(f"DEBUG: MQTT username = {self.link.username}")
        return self
