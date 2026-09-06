from gwsproto.data_classes.components.component import DeviceComponent
from gwsproto.enums import SimDeviceType
from gwsproto.errors import DcError
from gwsproto.named_types import ScadaBoardComponentGt
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt


class ScadaBoardComponent(DeviceComponent[ScadaBoardComponentGt, ScadaDeviceTypeGt]):
    """The only device types a scada board carries today are gw.scada.device.type
    records, and the layout's BoardResolution axiom guarantees the record
    exists — so device_type is required and never None."""

    device_type: ScadaDeviceTypeGt

    def __init__(
        self, gt: ScadaBoardComponentGt, device_type: ScadaDeviceTypeGt
    ) -> None:
        if not isinstance(device_type, ScadaDeviceTypeGt):
            raise DcError(
                f"ScadaBoardComponent <{gt.ComponentId}> requires a "
                f"gw.scada.device.type record; got {type(device_type).__name__}"
            )
        super().__init__(gt, device_type)

    @property
    def simulated(self) -> bool:
        """The board is a simulated device: its record's DeviceType is a
        gw1.sim.device.type value (SimGw108). Board-resident actors take real
        or fake silicon from this, never from a runtime flag."""
        return self.device_type.DeviceType in SimDeviceType.values()
