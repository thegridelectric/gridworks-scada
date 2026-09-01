import importlib
from gwsproto.enums import ActorClass, ActuationAuthority, SeasonalStorageMode
from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface


class LocalControl(ShNodeActor):
    """Selection facade: picks WHICH LocalControl implementation runs.

    Two selection axes, in order: the LAYOUT FAMILY first (the layout says
    what kind of house this is — a Nolan house needs Nolan control however
    it is currently operating), then the ops-artifact mode within the
    family (the ops file says how the house should operate right now)."""

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        node = services.hardware_layout.node(name)
        if node is None:
            raise Exception("Expect a LocalControl node!")
        if node.ActorClass != ActorClass.LocalControl:
            raise Exception("Expects ActorClass LocalControl!")

        layout = services.hardware_layout
        strategy = layout.hydronic.Strategy
        authority = self.ops.ActuationAuthority
        seasonal_storage_mode = self.ops.SeasonalStorageMode

        # Dynamically load the implementation class
        if strategy == "Nolan":
            module = importlib.import_module("actors.local_control.nolan")
            impl_class = getattr(module, "NolanLocalControl")
        elif authority == ActuationAuthority.Standby:
            module = importlib.import_module("actors.local_control.house0.standby")
            impl_class = getattr(module, "StandbyLocalControl")
        elif seasonal_storage_mode == SeasonalStorageMode.AllTanks:
            module = importlib.import_module("actors.local_control.house0.all_tanks_tou")
            impl_class = getattr(module, "AllTanksTouLocalControl")
        elif seasonal_storage_mode == SeasonalStorageMode.BufferOnly:
            module = importlib.import_module("actors.local_control.house0.buffer_only_tou")
            impl_class = getattr(module, "BufferOnlyTouLocalControl")
        else:
            raise Exception(f"Unknown setup ActuationAuthority {authority}, "
                            f"SeasonalStorageMode {seasonal_storage_mode}")

        # Create the implementation instance
        self._impl = impl_class(name, services)
        services.logger.error(f"Creating LocalControl with actuation authority {authority} and seasonal "
                              f"storage mode {seasonal_storage_mode}, using {impl_class.__module__}.{impl_class.__name__}")

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
