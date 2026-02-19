from pydantic import BaseModel, ConfigDict, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import MakeModel
from gwsproto.property_format import UUID4Str
from gwsproto.type_helpers import CACS_BY_MAKE_MODEL


class ComponentAttributeClassGt(BaseModel):
    ComponentAttributeClassId: UUID4Str
    DisplayName: str | None = None
    MakeModel: MakeModel
    MinPollPeriodMs: PositiveInt | None = None
    TypeName: str = "component.attribute.class.gt"
    Version: str = "001"

    model_config = ConfigDict(use_enum_values=True, extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Component Attribute Classes captured by MakeModel
                If cac is a ComponentAttributeClassGt,
        then
           - EITHER  its (MakeModel, ComponentAttributeClassId) must be a key,value pair in
        CACS_BY_MAKE_MODEL (below)
           - XOR its MakeModel is MakeModel.UNKNOWNMAKE__UNKNOWNMODEL

        CACS_BY_MAKE_MODEL: Dict[MakeModel, str] = {
            MakeModel.EGAUGE__4030: '739a6e32-bb9c-43bc-a28d-fb61be665522',
            MakeModel.NCD__PR814SPST: 'c6e736d8-8078-44f5-98bb-d72ca91dc773',
            MakeModel.ADAFRUIT__642: '43564cd2-0e78-41a2-8b67-ad80c02161e8',
            MakeModel.GRIDWORKS__WATERTEMPHIGHPRECISION: '7937eb7e-24d5-4d52-990f-cca063484df9',
            MakeModel.GRIDWORKS__SIMPM1: '28897ac1-ea42-4633-96d3-196f63f5a951',
            MakeModel.SCHNEIDERELECTRIC__IEM3455: '6bcdc388-de10-40e6-979a-8d66bfcfe9ba',
            MakeModel.GRIDWORKS__SIMBOOL30AMPRELAY: '69f101fc-22e4-4caa-8103-50b8aeb66028',
            MakeModel.OPENENERGY__EMONPI: '357b9b4f-2550-4380-aa6b-d2cd9c7ba0f9',
            MakeModel.GRIDWORKS__SIMTSNAP1: 'b9f7135e-07a9-42f8-b847-a9bb3ea3770a',
            MakeModel.ATLAS__EZFLO: '13d916dc-8764-4b16-b85d-b8ead3e2fc80',
            MakeModel.HUBITAT__C7__LAN1: '62528da5-b510-4ac2-82c1-3782842eae07',
            MakeModel.GRIDWORKS__TANK_MODULE_1: '60ac199d-679a-49f7-9142-8ca3e6428a5f',
            MakeModel.FIBARO__ANALOG_TEMP_SENSOR: '7ce0ce69-14c6-4cb7-a33f-2aeca91e0680',
            MakeModel.AMPHENOL__NTC_10K_THERMISTOR_MA100GG103BN: '2821c81d-054d-4003-9b07-2c295aef40f5',
            MakeModel.YHDC__SCT013100: '812761ba-6544-4796-9aad-e1c979f58734',
            MakeModel.MAGNELAB__SCT0300050: 'cf312bd6-7ca5-403b-a61b-b2e817ea1e22',
            MakeModel.GRIDWORKS__MULTITEMP1: '432073b8-4d2b-4e36-9229-73893f33f846',
            MakeModel.KRIDA__EMR16I2CV3: '018d9ffb-89d1-4cc4-95c0-f170711b5ffa',
            MakeModel.OMEGA__FTB8007HWPT: '8cf6c726-e38a-4900-9cfe-ae6f053aafdf',
            MakeModel.ISTEC_4440: '62ed724c-ba62-4302-ae30-d52b20d42ad9',
            MakeModel.OMEGA__FTB8010HWPT: 'd9f225f8-eeb5-4cb7-b314-5551b925ea27',
            MakeModel.BELIMO__BALLVALVE232VS: 'a2236d8c-7c9b-403f-9c55-733c62971d09',
            MakeModel.BELIMO__DIVERTERB332L: 'f3261ed0-3fb1-4def-b60b-246960bf85ef',
            MakeModel.TACO__0034EPLUS: '3880ba73-61e5-4b35-9df1-e154a03a3335',
            MakeModel.TACO__007E: '198ebac8-e0b9-4cee-ae91-2ee6db708491',
            MakeModel.ARMSTRONG__COMPASSH: 'ff6863e1-d5f7-4066-8579-2768162321a6',
            MakeModel.HONEYWELL__T6ZWAVETHERMOSTAT: '03533a1f-3cb9-4a1f-8d57-690c0ad0475b',
            MakeModel.PRMFILTRATION__WM075: '61d5c12d-eeca-4835-9a11-e61167d82e0d',
            MakeModel.BELLGOSSETT__ECOCIRC20_18: '0d2ccc36-d2b8-405d-a257-3917111607c5',
            MakeModel.TEWA__TT0P10KC3T1051500: '20779dbb-0302-4c36-9d60-e1962857c2f3',
            MakeModel.EKM__HOTSPWM075HD: 'e52cb571-913a-4614-90f4-5cc81f8e7fe5',
            MakeModel.GRIDWORKS__SIMMULTITEMP: '627ac482-24fe-46b2-ba8c-3d6f1e1ee069',
            MakeModel.GRIDWORKS__SIMTOTALIZER: 'a88f8f4c-fe1e-4645-a7f4-249912131dc8',
            MakeModel.KRIDA__DOUBLEEMR16I2CV3: '29eab8b1-100f-4230-bb44-3a2fcba33cc3',
            MakeModel.GRIDWORKS__TANKMODULE3: 'cbe49338-5d14-47ff-b05e-22031876962e',
        }
        """
        if (
            self.MakeModel not in CACS_BY_MAKE_MODEL
            and self.MakeModel is not MakeModel.default().value
        ):
            raise ValueError(
                "Axiom 1 violated! If MakeModel not in this list, "
                f"must be UNKNOWN: {CACS_BY_MAKE_MODEL}"
            )
        if self.MakeModel is MakeModel.default().value:
            if self.ComponentAttributeClassId in CACS_BY_MAKE_MODEL.values():
                raise ValueError(
                    f"Id {self.ComponentAttributeClassId} already used by known MakeModel!"
                )
        elif self.ComponentAttributeClassId != CACS_BY_MAKE_MODEL[self.MakeModel]:
            raise ValueError(
                f"Axiom 1 violated! MakeModel {self.MakeModel} must have "
                f"id {CACS_BY_MAKE_MODEL[self.MakeModel]}!"
            )
        return self
