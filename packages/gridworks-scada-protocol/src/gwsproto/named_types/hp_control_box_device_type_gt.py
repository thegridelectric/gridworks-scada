from typing import Literal, Optional

from pydantic import ConfigDict, PositiveFloat

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class HpControlBoxDeviceTypeGt(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/hp.control.box.device.type.gt/000
    """

    DeviceType: str
    DisplayName: Optional[str] = None
    PrimaryPumpFactoryInstalled: bool
    PrimaryPumpOverridable: bool
    PrimaryPumpAlwaysOn: bool
    WaterPumpRatedAmps: Optional[PositiveFloat] = None
    BackupHeaterKwList: Optional[list[PositiveFloat]] = None
    Mca: Optional[PositiveFloat] = None
    Mop: Optional[PositiveFloat] = None
    ProductInfoUrl: Optional[str] = None
    TypeName: Literal["hp.control.box.device.type.gt"] = "hp.control.box.device.type.gt"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")
