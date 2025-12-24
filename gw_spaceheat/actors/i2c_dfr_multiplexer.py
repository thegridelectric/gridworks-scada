"""Implements I2cDfrMultiplexer"""
import asyncio
import time
import smbus2
from typing import Any, Dict, List, Optional, Sequence, cast

from gwproactor import  MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.data_classes.components.dfr_component import DfrComponent
from gwsproto.data_classes.house_0_layout import House0Layout
from gwproto.data_classes.sh_node import ShNode
from gwproto.message import Message
from gwproto.enums import ActorClass, MakeModel
from gwproto.named_types import AnalogDispatch, SingleReading
from gw.errors import DcError

from result import Err, Result
from actors.sh_node_actor import ShNodeActor
from gwsproto.named_types import ActuatorsReady
from scada_app_interface import ScadaAppInterface

DFR_OUTPUT_SET_RANGE = 0x01
DFR_OUTPUT_RANGE_10V = 17


SLEEP_STEP_SECONDS = 0.1
class I2cDfrMultiplexer(ShNodeActor):
    LOOP_S = 300
    node: ShNode
    component: DfrComponent
    layout: House0Layout
    _stop_requested: bool
    is_simulated: bool
    bus: Optional[Any]  # smbus2.bus()
    dfr_val: Dict[str, int] # voltage x 100 by node name
    my_dfrs: List[ShNode]

    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
    ):
        super().__init__(name, services)
        self.is_simulated = self.settings.is_simulated
        self.component = cast(DfrComponent, self.node.component)
        if self.component.cac.MakeModel == MakeModel.DFROBOT__DFR0971_TIMES2:
            if self.component.gt.I2cAddressList != [94, 95]:
                raise Exception("Expect i2c addresses 0x5e, 0x5f for dfr 010V")
        else:
            raise Exception(
                f"Expected {MakeModel.DFROBOT__DFR0971_TIMES2}, got {self.component.cac}"
            )
        
        # Make/model specific
        # Move into driver code if/when we get a second make/model
        self.first_i2c_addr = self.component.gt.I2cAddressList[0]
        self.second_i2c_addr = self.component.gt.I2cAddressList[1]
        self.is_simulated = self.services.settings.is_simulated
        if self.is_simulated:
            self.bus = None
        else:
            try:
                self.bus = smbus2.SMBus(1)
            except Exception as e:
                raise Exception("No i2c /dev/i2c-1 for dfr!!")
            if self.bus is None:
                raise Exception("No i2c bus object for dfr!!")
            try:
                self.bus.read_byte(self.first_i2c_addr)
                self.bus.read_byte(self.second_i2c_addr)
            except Exception as e:
                raise Exception(f"Trouble reading addresses! {e}")
            # TODO: look for objects at the addresses 94, 95

        dfr_nodes = [node for node in self.layout.nodes.values() if node.ActorClass == ActorClass.ZeroTenOutputer]
        dfr_node_names = [config.ChannelName for config in self.component.gt.ConfigList]
        if {node.name for node in dfr_nodes} != set(dfr_node_names):
            raise Exception("Mismatch between config channel names and dfr actors!")
        self.my_dfrs: List[ShNode] = dfr_nodes
        self.dfr_val = {}  # from dfr.nmae to value 0-100
        self.check_channels()
        self._stop_requested = False
        self.resend_dfr = {dfr.Name: False for dfr in self.my_dfrs}

    def initialize_board(self) -> None:
        self.log("INITILIZING I2C DFR MULTIPLEXER")
        if self.is_simulated:
            self.log("SIMULATED ... no actual i2c bus object")
        if not self.is_simulated:
            self.bus = smbus2.SMBus(1)
            self.initialize_range()

        for dfr in self.my_dfrs:
            dfr_config = next(
                    config
                    for config in self.component.gt.ConfigList
                    if config.ChannelName == dfr.name
                )
            init = dfr_config.InitialVoltsTimes100
            self.set_level(dfr, init)
    
    def initialize_range(self) -> None:
        try:
            self.bus.read_byte(self.first_i2c_addr)
            self.bus.write_word_data(self.first_i2c_addr, DFR_OUTPUT_SET_RANGE, DFR_OUTPUT_RANGE_10V)
        except Exception:
            raise Exception(f"Failed to find DFR at addr {self.first_i2c_addr}")
        try:
            self.bus.read_byte(self.second_i2c_addr)
            self.bus.write_word_data(self.second_i2c_addr, DFR_OUTPUT_SET_RANGE, DFR_OUTPUT_RANGE_10V)
        except Exception:
            print("No second dfr")
            #raise Exception(f"Failed to find DFR at addr {self.second_i2c_addr}")

    def get_idx(self, dfr: ShNode) -> Optional[int]:
        if not dfr.actor_class == ActorClass.ZeroTenOutputer:
            return None
        dfr_config = next(
            (
                config
                for config in self.component.gt.ConfigList
                if config.ChannelName == dfr.name
            ),
            None,
        )
        if dfr_config is None:
            return None
        return dfr_config.OutputIdx

    def check_channels(self) -> None:
        #Channel names should equal node names for my_dfrs
        for dfr in self.my_dfrs:
            if not dfr.actor_class == ActorClass.ZeroTenOutputer:
                raise Exception(f"node {dfr} should have actor class ZeroTenOutputer!")
            dfr_config = next(
                (
                    config
                    for config in self.component.gt.ConfigList
                    if config.ChannelName == dfr.name
                ),
                None,
            )
            if dfr_config is None:
                raise Exception(f"relay {dfr} does not have a state channel!")
            if dfr_config.ChannelName != dfr.name:
                raise DcError(f"Channel name {dfr_config.ChannelName} must be node name {dfr.name}!")
    
    def set_level(self, dfr: ShNode, value: int) -> None:
        """
        value: (int): An integer between 0 and 100 representing 
        voltage x 10. 

        node: (ShNode): the dfr node getting dispatched
        """
        self.dfr_val[dfr.name] = value
        try:
            if not self.is_simulated:
                GP8403_CONFIG_CURRENT_REG = 0x02
                if dfr not in self.my_dfrs:
                    raise Exception(f"Only call for one of my dfr nodes: {self.my_dfrs}")
                idx = self.get_idx(dfr)
                data = int(float(4095 * value / 100)) << 4
                if idx == 1:
                    self.bus.write_word_data(self.first_i2c_addr, GP8403_CONFIG_CURRENT_REG, data)
                elif idx == 2:
                    self.bus.write_word_data(self.first_i2c_addr, GP8403_CONFIG_CURRENT_REG << 1, data)
                elif idx == 3:
                    self.bus.write_word_data(self.second_i2c_addr, GP8403_CONFIG_CURRENT_REG, data)
                elif idx == 4:
                    self.bus.write_word_data(self.second_i2c_addr, GP8403_CONFIG_CURRENT_REG << 1, data)
                else:
                    self.log(f"That's strange, got dfr idx {idx}")
            self.resend_dfr[dfr.Name] = False
            self.log(f"Set {dfr.name} to {value}")
            self._send_to(self.primary_scada,
            SingleReading(
                    ChannelName=dfr.name,
                    Value=value,
                    ScadaReadTimeUnixMs=int(time.time() * 1000),
                )    
            )
        except Exception as e:
            self.resend_dfr[dfr.Name] = True
            self.log(f"Trouble setting dfr level for {dfr.Name}!: {e}")

    def process_analog_dispatch(self, dispatch: AnalogDispatch) -> None:
        if not self.layout.node_by_handle(dispatch.FromHandle):
            self.log(f"Ignoring dispatch from  handle {dispatch.FromHandle} - not in layout!!")
            return
            #raise Exception(f"{dispatch.FromName} not in layout!!")
        if dispatch.ToHandle != self.node.handle:
            self.log(f"Ignoring dispatch {dispatch} - ToHandle is not {self.node.handle}!")
            return
        dfr = self.layout.node_by_handle(dispatch.FromHandle)
        if dfr not in self.my_dfrs:
            self.log(f"Ignoring dispatch {dispatch} - not from one of my dfrs! {self.my_dfrs}")
            return
        if dispatch.Value not in range(101):
            self.log(f"Igonring dispatch {dispatch} - range out of value. Should be 0-100")
            return
        if dispatch.AboutName != dfr.name:
           self.log("dispatch from dfr node: AboutHandle should match FromNode")

        self.set_level(dfr, dispatch.Value)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        if isinstance(message.Payload, AnalogDispatch):
            try:
                self.process_analog_dispatch(message.Payload)
            except Exception as e:
                self.log(f"Trouble with process_analog_dispatch: {e}")
        return Err(
            ValueError(
                f"Error. Dfr Multiplexer {self.name} receieved unexpected message: {message.Header}"
            )
        )

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.LOOP_S * 2)]

    async def maintain_dfr_states(self):
        await asyncio.sleep(2)
        for dfr in self.my_dfrs:
            self.set_level(dfr, self.dfr_val[dfr.name])
        last_set = time.time() 

        while not self._stop_requested:
            if time.time() - last_set > self.LOOP_S:
                for dfr in self.my_dfrs:
                    self.set_level(dfr, self.dfr_val[dfr.name])
                self._send(PatInternalWatchdogMessage(src=self.name))
                last_set = time.time()

            for dfr in self.my_dfrs:
                if self.resend_dfr[dfr.name]:
                    self.set_level(dfr, self.dfr_val[dfr.name])
            await asyncio.sleep(2) 

    def start(self) -> None:
        try:
            self.initialize_board()
        except Exception as e:
            raise Exception(f"Failure initializing board! {e}")
        self.services.add_task(
            asyncio.create_task(
                self.maintain_dfr_states(), name="maintain_dfr_states"
            )
        )
        self._send_to(self.primary_scada, ActuatorsReady())

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
