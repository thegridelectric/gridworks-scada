"""Makes gt.temp.sensor.cac.100 type"""
import json
from typing import Optional
from data_classes.cacs.temp_sensor_cac import TempSensorCac

from schema.gt.gt_temp_sensor_cac.gt_temp_sensor_cac import GtTempSensorCac
from schema.errors import MpSchemaError
from schema.enums import (
    TelemetryName,
    TelemetryNameMap,
)
from schema.enums import (
    Unit,
    UnitMap,
)
from schema.enums import (
    MakeModel,
    MakeModelMap,
)


class GtTempSensorCac_Maker:
    type_alias = "gt.temp.sensor.cac.100"

    def __init__(self,
                 telemetry_name: TelemetryName,
                 temp_unit: Unit,
                 make_model: MakeModel,
                 component_attribute_class_id: str,
                 exponent: int,
                 typical_response_time_ms: int,
                 display_name: Optional[str],
                 comms_method: Optional[str]):

        gw_tuple = GtTempSensorCac(
            TelemetryName=telemetry_name,
            DisplayName=display_name,
            TempUnit=temp_unit,
            MakeModel=make_model,
            ComponentAttributeClassId=component_attribute_class_id,
            Exponent=exponent,
            CommsMethod=comms_method,
            TypicalResponseTimeMs=typical_response_time_ms,
            #
        )
        gw_tuple.check_for_errors()
        self.tuple = gw_tuple

    @classmethod
    def tuple_to_type(cls, tuple: GtTempSensorCac) -> str:
        tuple.check_for_errors()
        return tuple.as_type()

    @classmethod
    def type_to_tuple(cls, t: str) -> GtTempSensorCac:
        try:
            d = json.loads(t)
        except TypeError:
            raise MpSchemaError("Type must be string or bytes!")
        if not isinstance(d, dict):
            raise MpSchemaError(f"Deserializing {t} must result in dict!")
        return cls.dict_to_tuple(d)

    @classmethod
    def dict_to_tuple(cls, d: dict) -> GtTempSensorCac:
        new_d = {}
        for key in d.keys():
            new_d[key] = d[key]
        if "TypeAlias" not in new_d.keys():
            raise MpSchemaError(f"dict {new_d} missing TypeAlias")
        if "TelemetryNameGtEnumSymbol" not in new_d.keys():
            raise MpSchemaError(f"dict {new_d} missing TelemetryNameGtEnumSymbol")
        new_d["TelemetryName"] = TelemetryNameMap.gt_to_local(new_d["TelemetryNameGtEnumSymbol"])
        if "DisplayName" not in new_d.keys():
            new_d["DisplayName"] = None
        if "TempUnitGtEnumSymbol" not in new_d.keys():
            raise MpSchemaError(f"dict {new_d} missing TempUnitGtEnumSymbol")
        new_d["TempUnit"] = UnitMap.gt_to_local(new_d["TempUnitGtEnumSymbol"])
        if "MakeModelGtEnumSymbol" not in new_d.keys():
            raise MpSchemaError(f"dict {new_d} missing MakeModelGtEnumSymbol")
        new_d["MakeModel"] = MakeModelMap.gt_to_local(new_d["MakeModelGtEnumSymbol"])
        if "ComponentAttributeClassId" not in new_d.keys():
            raise MpSchemaError(f"dict {new_d} missing ComponentAttributeClassId")
        if "Exponent" not in new_d.keys():
            raise MpSchemaError(f"dict {new_d} missing Exponent")
        if "CommsMethod" not in new_d.keys():
            new_d["CommsMethod"] = None
        if "TypicalResponseTimeMs" not in new_d.keys():
            raise MpSchemaError(f"dict {new_d} missing TypicalResponseTimeMs")

        gw_tuple = GtTempSensorCac(
            TypeAlias=new_d["TypeAlias"],
            TelemetryName=new_d["TelemetryName"],
            DisplayName=new_d["DisplayName"],
            TempUnit=new_d["TempUnit"],
            MakeModel=new_d["MakeModel"],
            ComponentAttributeClassId=new_d["ComponentAttributeClassId"],
            Exponent=new_d["Exponent"],
            CommsMethod=new_d["CommsMethod"],
            TypicalResponseTimeMs=new_d["TypicalResponseTimeMs"],
            #
        )
        gw_tuple.check_for_errors()
        return gw_tuple

    @classmethod
    def tuple_to_dc(cls, t: GtTempSensorCac) -> TempSensorCac:
        s = {
            "display_name": t.DisplayName,
            "component_attribute_class_id": t.ComponentAttributeClassId,
            "exponent": t.Exponent,
            "comms_method": t.CommsMethod,
            "typical_response_time_ms": t.TypicalResponseTimeMs,
            "telemetry_name_gt_enum_symbol": TelemetryNameMap.local_to_gt(t.TelemetryName),
            "temp_unit_gt_enum_symbol": UnitMap.local_to_gt(t.TempUnit),
            "make_model_gt_enum_symbol": MakeModelMap.local_to_gt(t.MakeModel),
            #
        }
        if s["component_attribute_class_id"] in TempSensorCac.by_id.keys():
            dc = TempSensorCac.by_id[s["component_attribute_class_id"]]
        else:
            dc = TempSensorCac(**s)
        return dc

    @classmethod
    def dc_to_tuple(cls, dc: TempSensorCac) -> GtTempSensorCac:
        if dc is None:
            return None
        t = GtTempSensorCac(
            TelemetryName=dc.telemetry_name,
            DisplayName=dc.display_name,
            TempUnit=dc.temp_unit,
            MakeModel=dc.make_model,
            ComponentAttributeClassId=dc.component_attribute_class_id,
            Exponent=dc.exponent,
            CommsMethod=dc.comms_method,
            TypicalResponseTimeMs=dc.typical_response_time_ms,
            #
        )
        t.check_for_errors()
        return t

    @classmethod
    def type_to_dc(cls, t: str) -> TempSensorCac:
        return cls.tuple_to_dc(cls.type_to_tuple(t))

    @classmethod
    def dc_to_type(cls, dc: TempSensorCac) -> str:
        return cls.dc_to_tuple(dc).as_type()

    @classmethod
    def dict_to_dc(cls, d: dict) -> TempSensorCac:
        return cls.tuple_to_dc(cls.dict_to_tuple(d))
