"""Implements I2cRelayMultiplexer Actors"""
import asyncio
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, cast

from gw.enums import GwStrEnum
# from actors.simple_sensor import SimpleSensor, SimpleSensorDriverThread
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.data_classes.components.i2c_multichannel_dt_relay_component import \
    I2cMultichannelDtRelayComponent

from gwproto.data_classes.data_channel import DataChannel
from data_classes.house_0_layout import House0Layout
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import (ActorClass, ChangeRelayPin, FsmActionType,
                           FsmReportType, MakeModel,
                           RelayEnergizationState, RelayWiringConfig,
                           TelemetryName)
from gwproto.message import Message
from gwproto.named_types import (SingleReading,
                                 SyncedReadings, FsmAtomicReport)
from pydantic import BaseModel, Field
from result import Err, Ok, Result
from actors.scada_interface import ScadaInterface
from actors.scada_actor import ScadaActor
from named_types import ActuatorsReady, FsmEvent, Glitch
from enums import LogLevel
class ChangeKridaPin(Enum):
    Energize = 0
    DeEnergize = 1


class KridaPinState(Enum):
    Energized = 0
    DeEnergized = 1


class SimulatedPin(BaseModel):
    value: int = Field(ge=0, le=1)


SLEEP_STEP_SECONDS = 0.1


class I2cRelayMultiplexer(ScadaActor):
    RELAY_MULTIPLEXER_LOGGER_NAME: str = "RelayMultiplexer"
    RELAY_LOOP_S = 60
    node: ShNode
    component: I2cMultichannelDtRelayComponent
    wiring_config: RelayWiringConfig
    event_enum: GwStrEnum
    layout: House0Layout
    _stop_requested: bool
    i2c_bus: Optional[Any]  # board.I2C()
    krida_board: Dict[int, Any]
    relay_state: Dict[int, RelayEnergizationState]
    my_relays: List[ShNode]

    def __init__(
        self,
        name: str,
        services: ScadaInterface,
    ):
        super().__init__(name, services)
        self.is_simulated = self.settings.is_simulated
        self.logger = services.logger.add_category_logger(
            self.RELAY_MULTIPLEXER_LOGGER_NAME,
            level=self.settings.relay_multiplexer_logging_level,
        )
        self.component = cast(I2cMultichannelDtRelayComponent, self.node.component)
        if self.component.cac.MakeModel != MakeModel.KRIDA__DOUBLEEMR16I2CV3:
            raise Exception(
                f"Expected {MakeModel.KRIDA__DOUBLEEMR16I2CV3}, got {self.component.cac}"
            )
        # Move into driver code if/when we get a second i2c relay component
        self.i2c_bus = None

        # krida_board[0] is the first krida board (# adafruit_pcf8575.PCF8575)
        # krida_board[1] is the second krida board
        self.krida_board: Dict[int, Any] = {}

        # A dict that controls the 32 pins
        self.krida_relay_pin: Dict[int, Any] = {}
        relay_node_names = [config.ActorName for config in self.component.gt.ConfigList]
        self.my_relays = [self.layout.nodes[name] for name in relay_node_names]
        # dict of current energization state
        self.relay_state: Dict[int, RelayEnergizationState] = {}
        self._stop_requested = False

    async def initialize_boards(self) -> None:
        if self.is_simulated:
            for relay in self.my_relays:
                idx = self.get_idx(relay)
                self.relay_state[idx] = RelayEnergizationState.DeEnergized
                self.krida_relay_pin[idx] = SimulatedPin(
                    value=KridaPinState.DeEnergized.value
                )
        else:
            # from starter-scripts/krida.py
            import adafruit_pcf8575
            import board

            self.i2c_bus = board.I2C()
            addresses = self.component.gt.I2cAddressList

            num_boards = 2
            for i in range(num_boards):
                setup_attempts = 0
                setup_done = False
                while setup_attempts < 3 and not setup_done:
                    wait_s = setup_attempts + 1
                    board_idx = i + 1
                    address = addresses[i]
                    try:
                        self.krida_board[board_idx] = adafruit_pcf8575.PCF8575(
                            i2c_bus=self.i2c_bus, address=address
                        )
                        self.logger.info(f"Found board at {address} for board {board_idx}")
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to get board at {address} for board {board_idx}: {e}"
                        )
                        await asyncio.sleep(wait_s)
                        continue

                    await asyncio.sleep(0.2)
                    self.logger.info(f"initializing board {board_idx} at {hex(address)}")
                    try:
                        for j in range(1, 17):
                            # set relay to correct pin, and switch to output. This energizes all relays
                            gw_idx = (board_idx - 1) * 16 + j
                            pin_idx = gw_to_pin(gw_idx)
                            self.krida_relay_pin[gw_idx] = self.krida_board[board_idx].get_pin(
                                pin_idx
                            )
                            self.krida_relay_pin[gw_idx].switch_to_output()
                        for j in range(1, 17):
                            # move all relays back to de-energized position
                            self.krida_relay_pin[
                                i * 16 + j
                            ].value = ChangeKridaPin.DeEnergize.value
                        # and record the de-energized state for all known relays
                        self.logger.info(f"Successfully initialized board {board_idx}")
                        setup_done = True
                    except Exception as e:
                        self.logger.warning(f"Trouble initializing board {board_idx}! {e}")
                        setup_attempts += 1
                        await asyncio.sleep(wait_s)
                # send up a Glitch if things took more than once
                if setup_attempts > 0:
                    if not setup_done:
                        for j in range(1,17):
                            gw_idx = (board_idx - 1) * 16 + j
                            self.krida_relay_pin[gw_idx] = SimulatedPin(
                                value=KridaPinState.DeEnergized.value
                            )
                        log_level = LogLevel.Critical
                        summary = f"i2c board {board_idx} ({hex(address)}) failed to initialize. Setting as simulated"

                    else: 
                        log_level = LogLevel.Info
                        summary = f"i2c board {board_idx} ({hex(address)}) took {setup_attempts+1} attempts to initialize! "
                        self._send_to(self.atn,
                                    Glitch(
                                        FromGNodeAlias=self.layout.scada_g_node_alias,
                                        Node=self.node.Name,
                                        Type=log_level,
                                        Summary=summary,
                                        Details="",
                                    )
                        )
                # finally, de-energize all relays
                self.log("De-energizing all the relays")
                for relay in self.my_relays:                        
                    self.relay_state[
                        self.get_idx(relay)
                    ] = RelayEnergizationState.DeEnergized

        # announce that the relays are ready
        self._send_to(self.primary_scada, ActuatorsReady())
        # and now start maintaining relay states
        self.services.add_task(
            asyncio.create_task(
                self.maintain_relay_states(), name="maintain_relay_states"
            )
        )

    def get_idx(self, relay: ShNode) -> int:
        if not relay.actor_class == ActorClass.Relay:
            raise Exception(f"That doesn't make sense! get_idx for {relay.name} should exist")
        relay_config = next(
            (
                config
                for config in self.component.gt.ConfigList
                if config.ActorName == relay.name
            ),
            None,
        )
        if relay_config is None:
            raise Exception(f"That doesn't make sense! relay_config for {relay.name} should exist")
        return relay_config.RelayIdx

    def get_channel(self, relay: ShNode) -> Optional[DataChannel]:
        if not relay.actor_class == ActorClass.Relay:
            return None
        relay_config = next(
            (
                config
                for config in self.component.gt.ConfigList
                if config.ActorName == relay.name
            ),
            None,
        )
        if relay_config is None:
            raise Exception(f"relay {relay} does not have a state channel!")
        return self.layout.data_channels[relay_config.ChannelName]

    def _dispatch_relay_pin(self, dispatch: FsmEvent) -> Result[bool, BaseException]:
        if dispatch.EventType != ChangeRelayPin.enum_name():
            return Ok(False)
        relay = self.layout.node_by_handle(dispatch.FromHandle)
        if relay is None:
            return Err(
                ValueError(f"message.FromHandle {dispatch.FromHandle} not in layout!")
            )
        ChangeRelayPin.Energize
        idx = self.get_idx(relay)
        if idx is None:
            return Err(ValueError(f"Not a valid relay: {relay}"))
        if idx not in self.relay_state:
            self.log("Relay board not initialized yet. Ignoring dispatch")
            return Ok(False)
        try:
            if dispatch.EventName == ChangeRelayPin.Energize.value:
                self.krida_relay_pin[idx].value = ChangeKridaPin.Energize.value
                self.relay_state[idx] = RelayEnergizationState.Energized
            else:
                self.krida_relay_pin[idx].value = ChangeKridaPin.DeEnergize.value
                self.relay_state[idx] = RelayEnergizationState.DeEnergized
        except Exception as e:
            return Err(ValueError(f"Trouble setting relay {idx} via i2c: {e}"))
        channel = self.get_channel(relay)
        if channel is None:
            raise Exception("Channel can't be None here")
        if channel.TelemetryName != TelemetryName.RelayState:
            raise Exception(
                "relay state channels should have telemetry name RelayState"
            )
        t_ms = int(time.time() * 1000)
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=channel.Name,
                Value=self.relay_state[idx].value,
                ScadaReadTimeUnixMs=t_ms,
            ),
        )
        self._send_to(
            relay,
            FsmAtomicReport(
                MachineHandle=self.node.handle,
                StateEnum="relay.pin",
                ReportType=FsmReportType.Action,
                ActionType=FsmActionType.RelayPinSet,
                Action=self.relay_state[idx].value,
                UnixTimeMs=t_ms,
                TriggerId=dispatch.TriggerId,
            ),
        )
        return Ok()

    def _process_event_message(self, message: FsmEvent) -> Result[bool, BaseException]:
        if message.ToHandle != self.node.handle:
            print(f"Not a message for {self.node.Handle}: {message}")
            return
        if message.EventType != ChangeRelayPin.enum_name():
            print(f"Not a ChangeRelayPin event type. Ignoring: {message}")
            return
        if message.EventName not in ChangeRelayPin.values():
            print(
                f"EventName {message.EventName} not in ChangeRelayPin values {ChangeRelayPin.values()}"
            )
            return
        self._dispatch_relay_pin(message)
        return Ok()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        if isinstance(message.Payload, FsmEvent):
            return self._process_event_message(message.Payload)
        return Err(
            ValueError(
                f"Error. Relay Multiplexer{self.name} receieved unexpected message: {message.Header}"
            )
        )

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.RELAY_LOOP_S * 2)]

    async def maintain_relay_states(self):
        first_time: bool = True
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            channel_names = []
            values = []
            for relay in self.my_relays:
                idx = self.get_idx(relay)
                channel_names.append(self.get_channel(relay).Name)
                if self.relay_state[idx] == RelayEnergizationState.Energized:
                    values.append(RelayEnergizationState.Energized.value)
                    if not first_time:
                        self.krida_relay_pin[idx].value = KridaPinState.Energized.value
                        # self.logger.info(f"Making sure {relay.name} is Energized")
                else:
                    values.append(RelayEnergizationState.DeEnergized.value)
                    if not first_time:
                        self.krida_relay_pin[idx].value = KridaPinState.DeEnergized.value
                        # self.logger.info(f"Making sure {relay.name} is DeEnergized")
            readings = SyncedReadings(
                ChannelNameList=channel_names,
                ValueList=values,
                ScadaReadTimeUnixMs=int(time.time() * 1000),
            )
            # if first_time:
            #     self.log("SENDING FIRST TIME!!")
            #     self.log(readings)
            self._send_to(self.primary_scada, readings)
            first_time = False
            await asyncio.sleep(self.RELAY_LOOP_S)

    def start(self) -> None:
        asyncio.create_task(self.initialize_boards())

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""

def krida_to_gw(krida_board: int, krida_idx: int) -> int:
    if krida_idx < 9:
        return krida_board * 16 + (9 - krida_idx)
    else:
        return krida_board * 16 + krida_idx


def gw_to_board_idx(gw_idx: int) -> int:
    return int((gw_idx - 1) / 16)


def board_from_gw_idx(gw_idx: int) -> int:
    return int((gw_idx - 1) / 16) + 1


def gw_to_pin(gw_idx: int) -> int:
    i = (gw_idx - 1) % 16 + 1
    krida_idx = 0
    if i < 9:
        krida_idx = 9 - i
    else:
        krida_idx = i
    return krida_idx - 1



