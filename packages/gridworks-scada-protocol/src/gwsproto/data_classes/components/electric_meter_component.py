from gwsproto.data_classes.components.component import Component
from gwsproto.named_types.electric_meter_device_type_gt import ElectricMeterDeviceTypeGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt


class ElectricMeterComponent(
    Component[ElectricMeterComponentGt, ElectricMeterDeviceTypeGt]
): ...
