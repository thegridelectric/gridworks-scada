import importlib

from gwproto import Message
from result import Ok, Result

from actors.sh_node_actor import ShNodeActor
from gwsproto.enums import SeasonalStorageMode
from gwsproto.named_types import AllyGivesUp, SlowDispatchContract
from scada_app_interface import ScadaAppInterface

class LeafAlly(ShNodeActor):
    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        # Dynamically load the implementation. 
        if self.layout.layout_type_name == "gw.nolan.layout":
            module = importlib.import_module("actors.leaf_ally.nolan")
            impl_class = getattr(module, "NolanLeafAlly")
        elif self.ops.FamilyParams.SeasonalStorageMode == SeasonalStorageMode.AllTanks:
            module = importlib.import_module("actors.leaf_ally.house0.all_tanks")
            impl_class = getattr(module, "AllTanksLeafAlly")
        elif self.ops.FamilyParams.SeasonalStorageMode == SeasonalStorageMode.BufferOnly:
            module = importlib.import_module("actors.leaf_ally.house0.buffer_only")
            impl_class = getattr(module, "BufferOnlyLeafAlly")
        else:
            raise Exception(f"SeasonalStorageMode {self.ops.FamilyParams.SeasonalStorageMode}")
        # Create the implementation instance
        self._impl = impl_class(name, services)
        services.logger.error(f"Creating LeafAlly with strategy {self.ops.FamilyParams.SeasonalStorageMode}, "
                              f"using {impl_class.__module__}.{impl_class.__name__}")

    # Forward all properties and methods to the implementation
    @property
    def state(self):
        return self._impl.state

    @property
    def prev_state(self):
        return self._impl.prev_state

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        """The dispatch refusal gate: while the ops word says the scada does
        not accept dispatch, every contract offer gets AllyGivesUp with the
        reason and never reaches the family's ally."""
        if isinstance(message.Payload, SlowDispatchContract) and not self.ops.AcceptsDispatch:
            reason = self.ops.DispatchRefusalReason
            self.log(f"Refusing dispatch contract: {reason}")
            self._send_to(
                self.primary_scada,
                AllyGivesUp(Reason=f"{reason}: not entering DispatchContracts"),
            )
            return Ok(True)
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
