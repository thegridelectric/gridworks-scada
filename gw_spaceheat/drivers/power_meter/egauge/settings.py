from enum import Enum

from pydantic import BaseModel


class ModbusClientSettings(BaseModel):
    host: str = ""
    port: int = 502
    unit_id: int = 1
    timeout: float = 30.0
    auto_open: bool = True
    auto_close: bool = False


class RegisterType(Enum):
    f32 = "f32"
    u32 = "u32"
    s64 = "s64"
    t16 = "t16"

class EGaugeRegister(BaseModel):
    Address: int
    Name: str
    Description: str
    Type: RegisterType
    Denominator: float
    Unit: str
    Deprecated: bool
    BaseAddress: int = 0

    @property
    def offset(self) -> int:
        return self.Address - self.BaseAddress
