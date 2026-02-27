import importlib
from gwsproto.enums import ActorClass, SeasonalStorageMode
from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

class LeafAlly(ShNodeActor):
    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        node = services.hardware_layout.node(name)
        if node is None:
            raise Exception("Missing the LeafAlly!!")
        if node.ActorClass != ActorClass.LeafAlly:
            raise Exception("Expects ActorClass LeafAlly!")

        # Dynamically load the implementation class based on LocalControl strategy
        if self.settings.seasonal_storage_mode == SeasonalStorageMode.AllTanks:
            module = importlib.import_module("actors.leaf_ally.all_tanks")
            impl_class = getattr(module, "AllTanksLeafAlly")
        elif self.settings.seasonal_storage_mode == SeasonalStorageMode.BufferOnly:
            module = importlib.import_module("actors.leaf_ally.buffer_only")
            impl_class = getattr(module, "BufferOnlyLeafAlly")
        else:
            raise Exception(f"SeasonalStorageMode {self.settings.seasonal_storage_mode}")
        # Create the implementation instance
        self._impl = impl_class(name, services)
        services.logger.error(f"Creating LeafAlly with strategy {self.settings.seasonal_storage_mode}, "
                              f"using {impl_class.__module__}.{impl_class.__name__}")

    # Forward all properties and methods to the implementation
    @property
    def state(self):
        return self._impl.state

    @property
    def prev_state(self):
        return self._impl.prev_state

    def process_message(self, message):
        return self._impl.process_message(message)

    def start(self):
        self._impl.start()

    def stop(self):
        self._impl.stop()

    async def join(self):
        await self._impl.join()

    @property
    def monitored_names(self):
        return self._impl.monitored_names
