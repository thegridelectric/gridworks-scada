from typing import Any

from pydantic import BaseModel


class WebServerGt(BaseModel):
    Name: str
    Host: str
    Port: int
    Serve: bool
    Kwargs: dict[str, Any] = {}
