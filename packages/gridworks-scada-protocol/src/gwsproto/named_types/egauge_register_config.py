from typing import Literal

from pydantic import BaseModel, Field


class EgaugeRegisterConfig(BaseModel):
    Address: int = Field(
        title="Address",
        description=(
            "EGauge's modbus holding address. Note that the EGauge modbus map for holding address "
            "100 will be 30100 - the '+30000' indicates it is a holding address. We use the 4-digit "
            "address after the '3'."
        ),
    )
    Name: str = Field(
        title="Name",
        description=(
            "The name assigned in the EGauge's modbus map. This is configured by the user (see "
            "URL)"
            "[More info](https://docs.google.com/document/d/1VeAt-V_AVqqiB0EVf-4JL_k_hVOsgbqldeAPVNwG1yI/edit#heading=h.7ct5hku166ut)"
        ),
    )
    Description: str = Field(
        title="Description",
        description="Again, assigned by the EGauge modbus map. Is usually 'change in value'",
    )
    Type: str = Field(
        title="Type",
        description=(
            "EGauge's numerical data type. Typically our power measurements are f32 ( 32-bit "
            "floating-point number). The serial number & firmware are t16 (which work to treat "
            "as 16-bit unsigned integer) and timestamps are u32 (32-bit unsigned integer)."
        ),
    )
    Denominator: int = Field(
        title="Denominator",
        description=(
            "Some of the modbus registers divide by 3.60E+06 (cumulative energy registers typically). "
            "For the power, current, voltage and phase angle the denominator is 1."
        ),
    )
    Unit: str = Field(
        title="Unit",
        description="The EGauge unit - typically A, Hz, or W.",
    )
    TypeName: Literal["egauge.register.config"] = "egauge.register.config"
    Version: Literal["000"] = "000"
