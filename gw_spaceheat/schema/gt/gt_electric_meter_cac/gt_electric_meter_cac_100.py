"""gt.electric.meter.cac.100 type"""

from schema.errors import MpSchemaError
from schema.gt.gt_electric_meter_cac.gt_electric_meter_cac_100_base import GtElectricMeterCac100Base


class GtElectricMeterCac100(GtElectricMeterCac100Base):

    def check_for_errors(self):
        errors = self.derived_errors() + self.hand_coded_errors()
        if len(errors) > 0:
            raise MpSchemaError(f" Errors making making gt.electric.meter.cac.100 for {self}: {errors}")

    def hand_coded_errors(self):
        return []
