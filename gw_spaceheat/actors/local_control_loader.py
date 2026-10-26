import importlib
from gwsproto.enums import SeasonalStorageMode, ServiceMode
from gwsproto.named_types import NolanLayout
from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface


class LocalControl(ShNodeActor):
    """Selection facade: picks WHICH LocalControl implementation runs.

    No authored field names the machine. The loader derives it from the
    ops word's Standby, the layout family, the family's SeasonalStorageMode
    and the ServiceMode; a row the table does not have raises, and a Nolan
    layout out of standby authoring Cooling raises NotImplementedError. Standby
    selects the shared standby machine whatever the family. The fields
    are read once at construction; a change is a restart."""

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        layout = services.hardware_layout
        standby = self.ops.Standby
        nolan = isinstance(layout.sema_layout, NolanLayout)
        seasonal_storage_mode = self.ops.FamilyParams.SeasonalStorageMode
        service_mode = self.ops.ServiceMode

        if standby:
            module = importlib.import_module("actors.local_control.standby")
            impl_class = getattr(module, "StandbyLocalControl")
        elif nolan and service_mode == ServiceMode.Cooling:
            raise NotImplementedError(
                "A Nolan layout has no cooling machine. The loop spruce ran in "
                "the summer of 2026 is spruce_summer_hack.py in the "
                "starter-scripts repo at commit 2c31bc1."
            )
        elif nolan and service_mode == ServiceMode.Heating and seasonal_storage_mode == SeasonalStorageMode.BufferOnly:
            module = importlib.import_module("actors.local_control.nolan.buffer_only_tou")
            impl_class = getattr(module, "NolanBufferOnlyTou")
        elif not nolan and service_mode == ServiceMode.Heating and seasonal_storage_mode == SeasonalStorageMode.AllTanks:
            module = importlib.import_module("actors.local_control.house0.all_tanks_tou")
            impl_class = getattr(module, "AllTanksTouLocalControl")
        elif not nolan and service_mode == ServiceMode.Heating and seasonal_storage_mode == SeasonalStorageMode.BufferOnly:
            module = importlib.import_module("actors.local_control.house0.buffer_only_tou")
            impl_class = getattr(module, "BufferOnlyTouLocalControl")
        else:
            raise Exception(
                f"No local control machine for Standby {standby}, "
                f"{layout.layout_type_name}, SeasonalStorageMode {seasonal_storage_mode}, "
                f"ServiceMode {service_mode}"
            )

        self._impl = impl_class(name, services)
        services.logger.error(
            f"Creating LocalControl (Standby {standby}, {layout.layout_type_name}, "
            f"SeasonalStorageMode {seasonal_storage_mode}, ServiceMode {service_mode}), "
            f"using {impl_class.__module__}.{impl_class.__name__}"
        )

    # Forward all properties and methods to the implementation
    @property
    def top_state(self):
        return self._impl.top_state

    def process_message(self, message):
        return self._impl.process_message(message)

    def start(self):
        self._impl.start()

    def stop(self):
        self._impl.stop()

    async def join(self):
        await self._impl.join()

    def init(self):
        self._impl.init()

    @property
    def monitored_names(self):
        return self._impl.monitored_names
