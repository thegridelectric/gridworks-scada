"""TempSensorComponent definition"""
from typing import Dict, Optional

from data_classes.components.temp_sensor_component_base import TempSensorComponentBase
from schema.gt.gt_temp_sensor_component.gt_temp_sensor_component import GtTempSensorComponent


class TempSensorComponent(TempSensorComponentBase):
    by_id: Dict[str, TempSensorComponentBase] =  TempSensorComponentBase._by_id

    def __init__(self, component_id: str,
                 component_attribute_class_id: str,
                 display_name: Optional[str] = None,
                 hw_uid: Optional[str] = None,
                 ):
        super(self.__class__, self).__init__(display_name=display_name,
                                             component_id=component_id,
                                             hw_uid=hw_uid,
                                             component_attribute_class_id=component_attribute_class_id,
                                             )

    def _check_update_axioms(self, type: GtTempSensorComponent):
        pass

    def __repr__(self):
        return f"{self.display_name}  ({self.cac.make_model.value})"
