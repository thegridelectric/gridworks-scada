import time
import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StrictInt

from gwsproto.enums import MarketPriceUnit
from gwsproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str


class FloParamsHouse0(BaseModel):
    GNodeAlias: LeftRightDotStr
    FloParamsUid: UUID4Str = Field(default_factory=lambda: str(uuid.uuid4()))
    TimezoneStr: str = "America/New_York"
    StartUnixS: UTCSeconds
    HorizonHours: PositiveInt = 48
    NumLayers: PositiveInt = 27
    # Equipment
    StorageVolumeGallons: PositiveInt = 360
    StorageLossesPercent: float = 0.5
    HpMinElecKw: float = -0.5
    HpMaxElecKw: float = 11
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
    CopIntercept: float
    CopOatCoeff: float
    CopLwtCoeff: float
    CopMin: float
    CopMinOatF: float
    # Plan stability penalty
    PreviousPlanHpKwhElList: list[float] | None = None
    PreviousEstimateStorageKwhNow: float | None = None
    StabilityWeight: float = 0.5
    StabilityDecay: float = 0.9
    StabilityThresholdKwh: float = 10.0
    StabilityHorizonHours: int = 20
    PriceUnit: MarketPriceUnit = MarketPriceUnit.USDPerMWh
    ParamsGeneratedS: UTCSeconds = Field(default_factory=lambda: int(time.time()))
    ConstantDeltaT: StrictInt = 20
    TypeName: Literal["flo.params.house0"] = "flo.params.house0"
    Version: Literal["005"] = "005"

    model_config = ConfigDict(extra="allow", frozen=True, use_enum_values=True)

    @property
    def total_price_forecast(self) -> list[float]:
        """
        returns reg + dist + lmp in USDPerMwh
        """
        if not self.PriceUnit == MarketPriceUnit.USDPerMWh:
            raise Exception("Expecting prices of USD per MWh")
        reg_usd_per_mwh = self.RegPriceForecast[:self.HorizonHours]
        dist_usd_per_mwh = self.DistPriceForecast[:self.HorizonHours]
        lmp_usd_per_mwh = self.LmpForecast[:self.HorizonHours]
        return [rp + dp + lmp for rp, dp, lmp in zip(
            reg_usd_per_mwh, dist_usd_per_mwh, lmp_usd_per_mwh, strict=True
        )]

    def COP(self, oat: float) -> float:
        """
        Coefficient of Performance as function of Outside Air Temp in F
        """
        if oat < self.CopMinOatF:
            return self.CopMin
        else:
            return self.CopIntercept + self.CopOatCoeff * oat
