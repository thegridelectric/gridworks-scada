from gwsproto.data_classes.components.component import Component
from gwsproto.named_types.electric_meter_cac_gt import ElectricMeterCacGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt


class ElectricMeterComponent(
    Component[ElectricMeterComponentGt, ElectricMeterCacGt]
): ...
