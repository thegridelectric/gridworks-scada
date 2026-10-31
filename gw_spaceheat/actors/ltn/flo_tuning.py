"""
LTN-owned Bruce optimizer knobs not supplied by ha1.params or runtime state.
The LTN maps these into HeatPumpWaterTankParams when starting a FLO run.
"""

STORAGE_LOSSES_PERCENT: float = 0.5
HP_MIN_KW_ELEC: float = -0.5
HP_MAX_KW_TH: float = 25
MAX_LOAD_KW_TH: float = 20
HP_CONSTANT_LIFT_F: float = 20

RSWT_PENALTY_ENABLED: bool = True
RSWT_PENALTY_WEIGHT: float = 0.5
RSWT_PENALTY_DECAY: float = 0.9
RSWT_PENALTY_EXPONENT_RATE: float = 0.03
RSWT_PENALTY_DECAY_MAX_HOUR: int = 12

STABILITY_PENALTY_ENABLED: bool = True
STABILITY_PENALTY_WEIGHT: float = 0.5
STABILITY_PENALTY_DECAY: float = 0.75
STABILITY_PENALTY_THRESHOLD_KWH: float = 10.0
STABILITY_PENALTY_THRESHOLD_PRICE_MWH: float = 15.0
STABILITY_PENALTY_HORIZON_HOURS: int = 20
