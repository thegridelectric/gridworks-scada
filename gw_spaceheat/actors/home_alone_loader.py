# Modify actors/home_alone.py to be a loader module
import importlib
from gwproto.enums import ActorClass
from enums import HomeAloneStrategy
from actors.scada_actor import ScadaActor
from actors.scada_interface import ScadaInterface

class HomeAlone(ScadaActor):
    def __init__(self, name: str, services: ScadaInterface):
        super().__init__(name, services)
        node = services.hardware_layout.node(name)
        # Get node from services
        node = services.hardware_layout.node(name)
        if node.ActorClass != ActorClass.HomeAlone:
            raise Exception("Expects ActorClass HomeAlone!")
        # Extract strategy field
        strategy = HomeAloneStrategy(getattr(node, "Strategy", None))

        # Dynamically load the implementation class
        if strategy == HomeAloneStrategy.WinterTou:
            module_name = "actors.home_alone.winter_tou"
        elif strategy == HomeAloneStrategy.ShoulderTou:
            module_name = "actors.home_alone.shoulder_tou"
        else:
            raise Exception(f"Unknown strategy {strategy}")

        module = importlib.import_module(module_name)
        impl_class = getattr(module, "HomeAlone")

        # Create the implementation instance
        self._impl = impl_class(name, services)
        services.logger.error(f"Creating HomeAlone with strategy: {strategy.value}, using {impl_class.__module__}.{impl_class.__name__}")

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