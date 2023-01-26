import csv
import struct
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional
from typing import Tuple

from pydantic import BaseModel
from pyModbusTCP.client import ModbusClient
from rich.table import Table


def repack(response: list[int], pack_format:str, unpack_format:str) -> Tuple[bytes, Any]:
    packed = struct.pack(pack_format, *response)
    return packed, struct.unpack(unpack_format, packed)[0]

def read(c: ModbusClient, addr: int, num_regs:int, pack_format:str, unpack_format:str) -> Tuple[list[int], bytes, Any]:
    regs = c.read_input_registers(addr, num_regs)
    packed, unpacked = repack(regs, pack_format, unpack_format)
    return regs, packed, unpacked

def readF32(c: ModbusClient, addr: int) -> Tuple[list[int], bytes, float]:
    return read(c, addr, 2, ">HH", ">f")

def readU32(c: ModbusClient, addr: int) -> Tuple[list[int], bytes, int]:
    return read(c, addr, 2, ">HH", ">I")

def readS64(c: ModbusClient, addr: int) -> Tuple[list[int], bytes, int]:
    return read(c, addr, 4, ">HHHH", ">q")

def readT16(c: ModbusClient, addr: int) -> Tuple[list[int], bytes, bytes]:
    return read(c, addr, 8, ">HHHHHHHH", ">16s")

class RegisterType(Enum):
    f32 = "f32"
    u32 = "u32"
    s64 = "s64"
    t16 = "t16"

    @classmethod
    def read_function(cls, type_: "RegisterType") -> Callable:
        match type_:
            case RegisterType.f32:
                f = readF32
            case RegisterType.s64:
                f = readS64
            case RegisterType.u32:
                f = readU32
            case RegisterType.t16:
                f = readT16
            case _:
                raise ValueError(f"No read function for {type}")
        return f

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

class EGaugeRegisters:

    by_offset: dict[int, EGaugeRegister]
    base_address: int = 0

    @classmethod
    def from_csv(cls, path: str | Path, base_address: Optional[int] = None) -> "EGaugeRegisters":
        path = Path(path)
        if not path.exists():
            raise ValueError(f"ERROR csv path {path} does not exist")
        with path.open() as f:
            csv_reader = csv.DictReader(f)
            dicts = [row for row in csv_reader]
        return EGaugeRegisters(dicts, base_address)

    def __init__(self, registers: Optional[list[EGaugeRegister | dict]] = None, base_address: Optional[int] = None):
        if registers is None:
            registers = []
        registers_used: list[EGaugeRegister] = [
            register
            if isinstance(register, EGaugeRegister)
            else EGaugeRegister(**register)
            for register in registers
        ]
        if base_address is None:
            base_address = min(2**16 + 1, *[register.Address for register in registers_used])
        self.base_address = base_address
        self.by_offset = dict()
        for register in registers_used:
            self.add_register(register)

    def add_register(self, register: EGaugeRegister) -> None:
        register.BaseAddress = self.base_address
        self.by_offset[register.offset] = register

    def offsets(self) -> list[int]:
        return sorted(self.by_offset.keys())

    def registers(self) -> list[EGaugeRegister]:
        return [self.by_offset[offset] for offset in self.offsets()]

    def get_table(self) -> Table:
        table = Table()
        fields = EGaugeRegister.__fields__.keys()
        for field_name in fields:
            table.add_column(field_name)
        for register in self.registers():
            table.add_row(*[str(getattr(register, field)) for field in fields])
        return table

def read_register(c: ModbusClient, register: EGaugeRegister) -> Tuple[list[int], bytes, Any]:
    return RegisterType.read_function(register.Type)(c, register.offset)


