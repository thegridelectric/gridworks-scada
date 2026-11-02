from typing import Literal, Self
from pydantic import StrictFloat, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import SeasonalStorageMode
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.flo_optimal_path import FloOptimalPath
from sema_snapshot.sema.types.flo_tuning_alice import FloTuningAlice
from sema_snapshot.sema.types.flo_tuning_bruce import FloTuningBruce


class FloParams(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.params/001"""

    g_node_alias: LeftRightDot
    created_ms: UTCMilliseconds
    start_unix_s: UTCSeconds
    step_duration_minutes: list[PositiveInt]
    lmp_usd_mwh_list: list[StrictFloat]
    dist_usd_mwh_list: list[StrictFloat]
    oat_f_list: list[StrictFloat]
    load_kwh_list: list[StrictFloat]
    rswt_f_list: list[StrictFloat]
    weather_forecast_id: UUID4Str
    seasonal_storage_mode: SeasonalStorageMode
    tanks_modeled: PositiveInt
    gallons_per_tank: PositiveInt
    temp_sensors_per_tank: PositiveInt
    max_tank_temp_f: StrictFloat
    initial_top_temp_f: StrictFloat
    initial_middle_temp_f: StrictFloat
    initial_bottom_temp_f: StrictFloat
    initial_thermocline1: PositiveInt
    initial_thermocline2: PositiveInt
    hp_currently_on: bool
    hp_max_kw_el: StrictFloat
    hp_turn_on_minutes: PositiveInt
    cop_intercept: StrictFloat
    cop_oat_coeff: StrictFloat
    cop_lwt_coeff: StrictFloat
    cop_min: StrictFloat
    cop_min_oat_f: StrictFloat
    price_max_usd_mwh: StrictFloat
    price_min_usd_mwh: StrictFloat
    previous_optimal_path: FloOptimalPath | None = None
    previous_estimate_elec_usd_mwh_now: StrictFloat | None = None
    tuning: FloTuningAlice | FloTuningBruce
    type_name: Literal["flo.params"] = "flo.params"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: StepListLengths
        StepDurationMinutes, LmpUsdMwhList, DistUsdMwhList, OatFList,
        LoadKwhList and RswtFList SHALL be non-empty and of the same length.
        """
        lengths = {
            "StepDurationMinutes": len(self.step_duration_minutes),
            "LmpUsdMwhList": len(self.lmp_usd_mwh_list),
            "DistUsdMwhList": len(self.dist_usd_mwh_list),
            "OatFList": len(self.oat_f_list),
            "LoadKwhList": len(self.load_kwh_list),
            "RswtFList": len(self.rswt_f_list),
        }
        if len(set(lengths.values())) != 1 or lengths["StepDurationMinutes"] == 0:
            raise ValueError(
                "Axiom 1 (StepListLengths) failed: the per-step lists must be "
                f"non-empty and of one length; got {lengths!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ThermoclinesWithinTheStore
        InitialThermocline1 SHALL be at most InitialThermocline2, and
        InitialThermocline2 SHALL be at most TempSensorsPerTank times
        TanksModeled.
        """
        top = self.temp_sensors_per_tank * self.tanks_modeled
        if not (self.initial_thermocline1 <= self.initial_thermocline2 <= top):
            raise ValueError(
                "Axiom 2 (ThermoclinesWithinTheStore) failed: need "
                f"InitialThermocline1 ({self.initial_thermocline1}) <= "
                f"InitialThermocline2 ({self.initial_thermocline2}) <= "
                f"TempSensorsPerTank * TanksModeled ({top})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: BufferIsOneTank
        If SeasonalStorageMode is BufferOnly, TanksModeled SHALL be 1.
        """
        if self.seasonal_storage_mode.value == "BufferOnly" and self.tanks_modeled != 1:
            raise ValueError(
                "Axiom 3 (BufferIsOneTank) failed: BufferOnly models one tank; "
                f"got TanksModeled {self.tanks_modeled}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: PriceBounds
        PriceMinUsdMwh SHALL be less than PriceMaxUsdMwh.
        """
        if not self.price_min_usd_mwh < self.price_max_usd_mwh:
            raise ValueError(
                f"Axiom 4 (PriceBounds) failed: PriceMinUsdMwh ({self.price_min_usd_mwh}) "
                f"must be less than PriceMaxUsdMwh ({self.price_max_usd_mwh})."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: PreviousRunTogether
        PreviousOptimalPath and PreviousEstimateElecUsdMwhNow SHALL be
        both present or both absent.
        """
        if (self.previous_optimal_path is None) != (
            self.previous_estimate_elec_usd_mwh_now is None
        ):
            raise ValueError(
                "Axiom 5 (PreviousRunTogether) failed: PreviousOptimalPath and "
                "PreviousEstimateElecUsdMwhNow must be both present or both absent."
            )
        return self
