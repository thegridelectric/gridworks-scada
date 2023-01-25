"""Base for gt.electric.meter.component.100"""
import json
from typing import List, NamedTuple, Optional
import schema.property_format as property_format


class GtElectricMeterComponentBase(NamedTuple):
    ComponentAttributeClassId: str
    ComponentId: str  #
    DisplayName: Optional[str] = None
    HwUid: Optional[str] = None
    PowerModbusRegister: Optional[int] = None
    IpAddress: Optional[str] = None
    TypeAlias: str = "gt.electric.meter.component.100"

    def as_type(self):
        return json.dumps(self.asdict())

    def asdict(self):
        d = self._asdict()
        if d["DisplayName"] is None:
            del d["DisplayName"]
        if d["HwUid"] is None:
            del d["HwUid"]
        if d["PowerModbusRegister"] is None:
            del d["PowerModbusRegister"]
        if d["IpAddress"] is None:
            del d["IpAddress"]
        return d

    def derived_errors(self) -> List[str]:
        errors = []
        if not isinstance(self.ComponentAttributeClassId, str):
            errors.append(
                f"ComponentAttributeClassId {self.ComponentAttributeClassId} must have type str."
            )
        if not property_format.is_uuid_canonical_textual(self.ComponentAttributeClassId):
            errors.append(
                f"ComponentAttributeClassId {self.ComponentAttributeClassId}"
                " must have format UuidCanonicalTextual"
            )
        if self.DisplayName:
            if not isinstance(self.DisplayName, str):
                errors.append(
                    f"DisplayName {self.DisplayName} must have type str."
                )
        if not isinstance(self.ComponentId, str):
            errors.append(
                f"ComponentId {self.ComponentId} must have type str."
            )
        if not property_format.is_uuid_canonical_textual(self.ComponentId):
            errors.append(
                f"ComponentId {self.ComponentId}"
                " must have format UuidCanonicalTextual"
            )
        if self.HwUid:
            if not isinstance(self.HwUid, str):
                errors.append(
                    f"HwUid {self.HwUid} must have type str."
                )
        if self.PowerModbusRegister:
            if not isinstance(self.PowerModbusRegister, int):
                errors.append(
                    f"PowerModbusRegister {self.PowerModbusRegister} must have type int."
                )
        if self.IpAddress:
            if not isinstance(self.IpAddress, str):
                errors.append(
                    f"IpAddress {self.IpAddress} must have type str."
                )
        if self.TypeAlias != "gt.electric.meter.component.100":
            errors.append(
                f"Type requires TypeAlias of gt.electric.meter.component.100, not {self.TypeAlias}."
            )

        return errors
