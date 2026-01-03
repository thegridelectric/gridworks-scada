from typing import Any

from pydantic import BaseModel

DEFAULT_WEB_SERVER_NAME = "default"


class WebServerGt(BaseModel):
    Name: str = DEFAULT_WEB_SERVER_NAME
    Host: str = "localhost"
    Port: int = 8080
    Enabled: bool = True
    Kwargs: dict[str, Any] = {}
