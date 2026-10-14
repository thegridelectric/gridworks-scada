"""Values a FLO run takes that neither a setting nor ha1.params supplies.

Every FloParamsHouse0 field is required on the wire; the LTN fills these
from here and the rest from its state, settings and ha1.params."""

from gwsproto.enums import MarketPriceUnit

STORAGE_LOSSES_PERCENT: float = 0.5
HP_MIN_ELEC_KW: float = -0.5
MAX_HP_KWH_TH: float = 25
MAX_LOAD_KWH_TH: float = 20
RSWT_PENALTY_ENABLED: bool = True
RSWT_PENALTY_WEIGHT: float = 0.5
RSWT_PENALTY_DECAY: float = 0.9
RSWT_PENALTY_EXPONENT_RATE: float = 0.03
RSWT_PENALTY_DECAY_MAX_HOUR: int = 12
STABILITY_PENALTY_ENABLED: bool = True
STABILITY_PENALTY_WEIGHT: float = 0.5
STABILITY_PENALTY_DECAY: float = 0.75
STABILITY_PENALTY_THRESHOLD_KWH: float = 10.0
STABILITY_PENALTY_HORIZON_HOURS: int = 20
PRICE_UNIT: MarketPriceUnit = MarketPriceUnit.USDPerMWh
CONSTANT_DELTA_T: int = 20
FLO_GIT_COMMIT_UNKNOWN: str = "Unknown"
