from typing import Literal, Optional

from pydantic import ConfigDict, PositiveFloat, PositiveInt

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class HpDeviceTypeGt(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/hp.device.type.gt/000
    """

    DeviceType: str
    DisplayName: Optional[str] = None
    MaxKwEl: PositiveFloat
    HeatingCapacityBtuHr: PositiveInt
    CoolingCapacityBtuHr: PositiveInt
    PrimaryPumpFactoryInstalled: bool
    PrimaryPumpOverridable: bool
    PrimaryPumpAlwaysOn: bool
    Refrigerant: Optional[str] = None
    CompressorRatedAmps: Optional[PositiveFloat] = None
    Mca: Optional[PositiveFloat] = None
    Mop: Optional[PositiveFloat] = None
    ProductInfoUrl: Optional[str] = None
    TypeName: Literal["hp.device.type.gt"] = "hp.device.type.gt"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")
