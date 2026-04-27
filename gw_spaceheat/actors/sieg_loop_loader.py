import importlib
from typing import Any
from enum import auto
from gwsproto.enums import ActorClass

from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

class SiegLoopMode:
    Fallback = auto()
    PidControl = auto()


class SiegLoop(ShNodeActor):
    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        node = services.hardware_layout.node(name)
        if node is None:
            raise Exception("Missing the SiegLoop!!")
        if node.ActorClass != ActorClass.SiegLoop:
            raise Exception("Expects ActorClass SiegLoop!")

        sieg_mode = SiegLoopMode.Fallback
        if sieg_mode == SiegLoopMode.Fallback:
            module = importlib.import_module("actors.sieg_loop.fallback")
            impl_class = getattr(module, "SiegLoopFallback")
        else:
            raise Exception(f"Sieg mode {sieg_mode}")

        self._impl = impl_class(name, services)
        services.logger.error(
            f"Creating SiegLoop with seasonal storage mode {sieg_mode}, "
            f"using {impl_class.__module__}.{impl_class.__name__}"
        )

    def __getattr__(self, attr_name: str) -> Any:
        impl = self.__dict__.get("_impl")
        if impl is None:
            raise AttributeError(attr_name)
        return getattr(impl, attr_name)

    @property
    def control_state(self):
        return self._impl.control_state

    @property
    def valve_state(self):
        return self._impl.valve_state

    @property
    def keep_seconds(self):
        return self._impl.keep_seconds

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
