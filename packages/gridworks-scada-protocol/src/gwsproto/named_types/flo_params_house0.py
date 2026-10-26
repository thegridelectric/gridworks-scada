from typing import List, Literal, Optional

from pydantic import ConfigDict, PositiveInt, StrictInt

from gwsproto.enums import MarketPriceUnit
from gwsproto.property_format import LeftRightDotStr, UTCSeconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloParamsHouse0(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.params.house0/007"""

    GNodeAlias: LeftRightDotStr
    FloParamsUid: UUID4Str
    TimezoneStr: str
    StartUnixS: UTCSeconds
    HorizonHours: PositiveInt
    NumLayers: PositiveInt
    # Equipment
    StorageVolumeGallons: PositiveInt
    StorageLossesPercent: float
    HpMinElecKw: float
    HpMaxElecKw: float
    HpTurnOnMinutes: int
    MaxHpKwhTh: float
    MaxLoadKwhTh: float
    # Initial state
    InitialTopTempF: StrictInt
    InitialMiddleTempF: StrictInt
    InitialBottomTempF: StrictInt
    InitialThermocline1: StrictInt
    InitialThermocline2: StrictInt
    HpIsOff: bool
    BufferAvailableKwh: float
    HouseAvailableKwh: float
    # Forecasts
    LmpForecast: Optional[List[float]] = None
    DistPriceForecast: Optional[List[float]] = None
    RegPriceForecast: Optional[List[float]] = None
    PriceForecastUid: UUID4Str
    OatForecastF: Optional[List[float]] = None
    WindSpeedForecastMph: Optional[List[float]] = None
    WeatherUid: UUID4Str
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
    # Penalties
    RswtPenaltyEnabled: bool
    StabilityPenaltyEnabled: bool
    # RSWT penalty
    RswtPenaltyWeight: float
    RswtPenaltyDecay: float
    RswtPenaltyExponentRate: float
    RswtPenaltyDecayMaxHour: int
    # Plan stability penalty
    PreviousPlanHpKwhElList: list[float] | None = None
    PreviousEstimateStorageKwhNow: float | None = None
    StabilityPenaltyWeight: float
    StabilityPenaltyDecay: float
    StabilityPenaltyThresholdKwh: float
    StabilityPenaltyHorizonHours: int
    # Other
    PriceUnit: MarketPriceUnit
    ParamsGeneratedS: UTCSeconds
    ConstantDeltaT: StrictInt
    FloGitCommit: str
    TypeName: Literal["flo.params.house0"] = "flo.params.house0"
    Version: Literal["007"] = "007"

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
