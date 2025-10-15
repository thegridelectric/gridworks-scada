import importlib
from gwproto.enums import ActorClass
from gwsproto.enums import HomeAloneStrategy
from actors.scada_actor import ScadaActor
from scada_app_interface import ScadaAppInterface

class AtomicAlly(ScadaActor):
    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        node = services.hardware_layout.node(name)
        if node.ActorClass != ActorClass.AtomicAlly:
            raise Exception("Expects ActorClass AtomicAlly!")
        
        # Read the HomeAlone strategy from the layout
        strategy = HomeAloneStrategy(getattr(services.hardware_layout, "ha_strategy", None))
        if strategy is None:
            raise Exception("Expect to have a HomeAlone strategy!!")

        # Dynamically load the implementation class based on HomeAlone strategy
        if strategy == HomeAloneStrategy.WinterTou:
            module = importlib.import_module("actors.atomic_ally.all_tanks")
            impl_class = getattr(module, "AllTanksAtomicAlly")
        else:
            module = importlib.import_module("actors.atomic_ally.buffer_only")
            impl_class = getattr(module, "BufferOnlyAtomicAlly")

        # Create the implementation instance
        self._impl = impl_class(name, services)
        services.logger.error(f"Creating AtomicAlly with HomeAlone strategy {strategy.value}, using {impl_class.__module__}.{impl_class.__name__}")

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

    @property
    def forecasts(self):
        return self._impl.forecasts
