from typing import Literal
from pydantic import ConfigDict, StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TempCalcMethod
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str


class SimPicoTankModuleComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/sim.pico.tank.module.component.gt/001"""

    component_id: UUID4Str
    device_type: PascalCase
    display_name: str | None = None
    hw_uid: str | None = None
    pico_hw_uid: str | None = None
    pico_a_hw_uid: str | None = None
    pico_b_hw_uid: str | None = None
    temp_calc_method: TempCalcMethod
    thermistor_beta: PositiveInt
    send_micro_volts: bool
    samples: PositiveInt
    num_sample_averages: PositiveInt
    pico_k_ohms: PositiveInt | None = None
    serial_number: str
    sensor_order: list[StrictInt] | None = None
    sim_life_s: PositiveInt | None = None
    sim_reboot_s: PositiveInt | None = None
    simulates_type_name: Literal["pico.tank.module.component.gt"] = (
        "pico.tank.module.component.gt"
    )
    simulates_version: Literal["012"] = "012"
    type_name: Literal["sim.pico.tank.module.component.gt"] = (
        "sim.pico.tank.module.component.gt"
    )
    version: Literal["001"] = "001"

    model_config = ConfigDict(**(SemaType.model_config | {"extra": "allow"}))

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SimPicoTankModuleComponentGt":
        """
        Axiom 1: PicoHardwareIdentityXor
        Exactly one of the following SHALL hold:
          - PicoHwUid is present
          - both PicoAHwUid and PicoBHwUid are present
        """
        single = self.pico_hw_uid is not None
        pair = self.pico_a_hw_uid is not None and self.pico_b_hw_uid is not None
        if single == pair:
            raise ValueError(
                "Axiom 1 (PicoHardwareIdentityXor): exactly one of PicoHwUid, "
                "or both PicoAHwUid and PicoBHwUid, SHALL be present."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "SimPicoTankModuleComponentGt":
        """
        Axiom 2: PicoKOhmsConsistency
        PicoKOhms SHALL be present if and only if TempCalcMethod equals SimpleBetaForPico.
        """
        kohms_present = self.pico_k_ohms is not None
        is_pico_beta = (
            str(getattr(self.temp_calc_method, "value", self.temp_calc_method))
            == "SimpleBetaForPico"
        )
        if kohms_present != is_pico_beta:
            raise ValueError(
                "Axiom 2 (PicoKOhmsConsistency): PicoKOhms SHALL be present "
                "if and only if TempCalcMethod is SimpleBetaForPico."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "SimPicoTankModuleComponentGt":
        """
        Axiom 3: SensorOrderPermutation
        If SensorOrder is present, it SHALL be a permutation of [1, 2, 3].
        """
        if self.sensor_order is not None and sorted(self.sensor_order) != [1, 2, 3]:
            raise ValueError(
                "Axiom 3 (SensorOrderPermutation): SensorOrder SHALL be a "
                "permutation of [1, 2, 3]."
            )
        return self
