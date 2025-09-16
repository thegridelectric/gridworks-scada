"""Type flo.params.house0, version 000"""
import time
import uuid
from typing import List, Literal, Optional

from gwsproto.enums import MarketPriceUnit
from gwproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StrictInt


class FloParamsHouse0(BaseModel):
    GNodeAlias: LeftRightDotStr
    FloParamsUid: UUID4Str = Field(default_factory=lambda: str(uuid.uuid4()))
    TimezoneStr: str = "America/New_York"
    StartUnixS: UTCSeconds
    HorizonHours: PositiveInt = 48
    NumLayers: PositiveInt = 24
    # Equipment
    StorageVolumeGallons: PositiveInt = 360
    StorageLossesPercent: float = 0.5
    HpMinElecKw: float = -0.5
    HpMaxElecKw: float = 11
    CopIntercept: float = 1.02
    CopOatCoeff: float = 0.0257
    CopLwtCoeff: float = 0
    CopMin: float = 1.4
    CopMinOatF: float = 15
    HpTurnOnMinutes: int = 10
    # Initial state
    InitialTopTempF: StrictInt
    InitialMiddleTempF: StrictInt
    InitialBottomTempF: StrictInt
    InitialThermocline1: StrictInt
    InitialThermocline2: StrictInt
    HpIsOff: bool = False
    BufferAvailableKwh: float = 0
    HouseAvailableKwh: float = 0
    # Forecasts
    LmpForecast: Optional[List[float]] = None
    DistPriceForecast: Optional[List[float]] = None
    RegPriceForecast: Optional[List[float]] = None
    PriceForecastUid: UUID4Str = Field(default_factory=lambda: str(uuid.uuid4()))
    OatForecastF: Optional[List[float]] = None
    WindSpeedForecastMph: Optional[List[float]] = None
    WeatherUid: UUID4Str = Field(default_factory=lambda: str(uuid.uuid4()))
    # House parameters
    AlphaTimes10: StrictInt
    BetaTimes100: StrictInt
    GammaEx6: StrictInt
    IntermediatePowerKw: float
    IntermediateRswtF: StrictInt
    DdPowerKw: float
    DdRswtF: StrictInt
    DdDeltaTF: StrictInt
    MaxEwtF: StrictInt
    PriceUnit: MarketPriceUnit = MarketPriceUnit.USDPerMWh
    ParamsGeneratedS: UTCSeconds = Field(default_factory=lambda: int(time.time()))
    # Flo type
    FloAlias: str = "Winter.Oak"
    FloGitCommit: str = "76e267b"
    TypeName: Literal["flo.params.house0"] = "flo.params.house0"
    Version: str = "003"

    model_config = ConfigDict(extra="allow", use_enum_values=True)
