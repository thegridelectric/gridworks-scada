# Modify actors/home_alone.py to be a loader module
import importlib
import sys
from typing import Any
from gwproto.enums import ActorClass
from enums import HomeAloneStrategy
from actors.scada_actor import ScadaActor
from actors.scada_interface import ScadaInterface

def _get_home_alone_class(strategy: HomeAloneStrategy = HomeAloneStrategy.Winter):
    """Dynamically determine which HomeAlone implementation to use"""
    if strategy == HomeAloneStrategy.Winter:
        winter_module = importlib.import_module("actors.home_alone.winter")
        return winter_module.HomeAlone
    elif strategy == HomeAloneStrategy.Shoulder:
        shoulder_module = importlib.import_module("actors.home_alone.shoulder")
        return shoulder_module.HomeAlone
    else:
        raise Exception(f"Do not have home alone strategy {strategy.value}!")


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
        if strategy == HomeAloneStrategy.Winter:
            module_name = "actors.home_alone.winter"
        else:
            module_name = "actors.home_alone.shoulder"

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