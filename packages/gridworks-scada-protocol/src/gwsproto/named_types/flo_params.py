from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator

from gwsproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str


class FloParams(BaseModel):
    """
    Base class for Forward Looking Optimizer params.

    Derived classes are expected to have TypeNames enforced as literals that start with flo.params.
    E.g. flo.params.brickstorageheater. This container is used for sending messages that include
    flo.params (i.e, flo.params.report

    [More info](https://gridworks-atn.readthedocs.io/en/latest/flo.html#flo-params)
    """

    GNodeAlias: LeftRightDotStr
    FloParamsUid: UUID4Str
    HomeCity: str
    TimezoneString: str
    StartUnixS: UTCSeconds
    TypeName: Literal["flo.params"] = "flo.params"
    Version: Literal["001"] = "001"

    model_config = ConfigDict(extra="allow")

    @field_validator("StartUnixS")
    @classmethod
    def check_start_unix_s(cls, v: int) -> int:
        """
        Axiom 1: StartS is 0 mod 300
        """
        # Implement Axiom(s)
        return v
