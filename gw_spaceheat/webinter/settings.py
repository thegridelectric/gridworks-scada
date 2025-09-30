import logging
import os
from pathlib import Path
from typing import Optional, Self
import dotenv
from gwproactor import AppSettings
from gwproactor.config import MQTTClient
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

class WebInterSettings(AppSettings):
    target_gnode: str = ""
    web_port: int = 8080
    web_host: str = "localhost"
    websocket_path: str = "/ws"
    link: MQTTClient = MQTTClient()
    verbosity: int = logging.WARN
    paho_verbosity: Optional[int] = None
    model_config = SettingsConfigDict(
        env_prefix="GWWEBINTER_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    def __init__(self, **kwargs):
        self._load_env_file()
        super().__init__(**kwargs)

    def _load_env_file(self):
        """Load .env file from current directory or project root"""

        # Find .env file
        current_dir = Path.cwd()
        env_file = current_dir / ".env"
        if not env_file.exists():
            print(f"Warning: No .env file found in {current_dir}")
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
        else:
            print("DEBUG: No .env file found")

    @model_validator(mode="after")
    def validate(self) -> Self:
        self.link.tls.use_tls = False        
        if os.getenv('GWWEBINTER__TARGET_GNODE'):
            self.target_gnode = os.getenv('GWWEBINTER__TARGET_GNODE')
            if len(self.target_gnode.split('.')) > 2:
                self.websocket_path = f'/ws{self.target_gnode.split('.')[-2]}'
            else:
                print(f"WARNING: Target gnode = {self.target_gnode}")
                self.websocket_path = f'/ws'
        if os.getenv('GWWEBINTER__LINK__HOST'):
            self.link.host = os.getenv('GWWEBINTER__LINK__HOST')
        if os.getenv('GWWEBINTER__LINK__PORT'):
            self.link.port = int(os.getenv('GWWEBINTER__LINK__PORT'))
        if os.getenv('GWWEBINTER__LINK__USERNAME'):
            self.link.username = os.getenv('GWWEBINTER__LINK__USERNAME')
        if os.getenv('GWWEBINTER__LINK__PASSWORD'):
            class SimpleSecret:
                def __init__(self, value):
                    self._value = value
                def get_secret_value(self):
                    return self._value
            self.link.password = SimpleSecret(os.getenv('GWWEBINTER__LINK__PASSWORD'))
        
        print(f"DEBUG: Target gnode = {self.target_gnode}")
        print(f"DEBUG: Use TLS = {self.link.tls.use_tls}")
        print(f"DEBUG: MQTT host = {self.link.host}")
        print(f"DEBUG: MQTT port = {self.link.port}")
        print(f"DEBUG: MQTT username = {self.link.username}")
        return self
