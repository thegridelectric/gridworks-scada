import asyncio
import datetime
import json
import logging
import re
import time
import uuid
from typing import Dict, Set, Optional
from dataclasses import dataclass

from aiohttp import web
from aiohttp.web import WebSocketResponse
from gwproto import Message as GWMessage
from gwproto import MQTTTopic
from data_classes.house_0_names import H0N
from gwproto.named_types import SendSnap
from paho.mqtt.client import MQTTMessageInfo
from result import Result

from webinter.settings import WebInterSettings
from admin.watch.clients.constrained_mqtt_client import ConstrainedMQTTClient
from admin.watch.clients.constrained_mqtt_client import MQTTClientCallbacks
from admin.watch.clients.admin_client import type_name
from named_types import LayoutLite, SendLayout, SnapshotSpaceheat, AdminDispatch, AdminKeepAlive, AdminReleaseControl, FsmEvent
from gwproto.named_types import SingleReading

module_logger = logging.getLogger(__name__)


@dataclass
class WebSocketMessage:
    type: str
    data: dict


class WebInterMQTTBridge:
    """Bridges WebSocket connections to MQTT broker"""
    
    def __init__(self, settings: WebInterSettings):
        self.settings = settings
        self.logger = module_logger
        self._mqtt_client: ConstrainedMQTTClient = None
        self._websocket_clients: Set[WebSocketResponse] = set()
        self._layout: LayoutLite = None
        self._snapshot: SnapshotSpaceheat = None
        self._relay_configs: Dict[str, dict] = {}
        self._channel_to_relay: Dict[str, str] = {}
        self._thermostat_names: list[str] = []
        
        # Synchronized timer state
        self._current_controller: Optional[str] = None
        self._control_timeout: Optional[int] = None
        self._control_start_time: Optional[float] = None
        self._timer_task: Optional[asyncio.Task] = None
        
        # Status tracking
        self._messages_received: int = 0
        self._last_activity_time: Optional[float] = None
        self._pending_snapshot_message: Optional[str] = None
        
    def _setup_mqtt_client(self):
        """Setup MQTT client to connect to RabbitMQ"""
        self.settings.link.tls.use_tls = False
        
        # Create subscription topic
        subscription_topic = MQTTTopic.encode(
            envelope_type=GWMessage.type_name(),
            src=self.settings.target_gnode,
            dst=H0N.admin,
            message_type="#",
        )
        print(f"DEBUG: Subscribing to MQTT topic: {subscription_topic}")
        
        self._mqtt_client = ConstrainedMQTTClient(
            settings=self.settings.link,
            subscriptions=[subscription_topic],
            callbacks=MQTTClientCallbacks(
                state_change_callback=self._mqtt_state_changed,
                message_received_callback=self._mqtt_message_received,
            ),
            logger=self.logger,
        )
    
    def _mqtt_state_changed(self, old_state: str, new_state: str) -> None:
        """Handle MQTT connection state changes"""
        self.logger.info(f"MQTT state changed: {old_state} -> {new_state}")
        if new_state == ConstrainedMQTTClient.States.active:
            self._request_layout_lite()
    
    def _mqtt_message_received(self, topic: str, payload: bytes) -> None:
        """Handle incoming MQTT messages"""
        try:
            print(f"DEBUG: MQTT message received on topic: {topic}")
            self._messages_received += 1
            self._last_activity_time = time.time()
            
            decoded_topic = MQTTTopic.decode(topic) 
            message = GWMessage.model_validate_json(payload)

            if decoded_topic.message_type == type_name(LayoutLite):
                print("DEBUG: Processing layout.lite message")
                self._process_layout_lite(payload)
            elif decoded_topic.message_type == type_name(SnapshotSpaceheat):
                print("DEBUG: Processing snapshot.spaceheat message")
                self._process_snapshot(payload)
            elif decoded_topic.message_type == type_name(SingleReading):
                self._process_single_reading(payload)
            
        except Exception as e:
            print(f"DEBUG: Error processing MQTT message: {e}")
            self.logger.exception(f"Error processing MQTT message: {e}")
    
    def _process_layout_lite(self, payload: bytes) -> None:
        """Process layout message to extract relay configurations"""
        message = GWMessage[LayoutLite].model_validate_json(payload)
        self._layout = message.Payload
        
        # Extract relay configurations
        self._relay_configs = {}
        relay_node_names = {node.Name for node in self._layout.ShNodes if node.ActorClass == 'Relay'}
        relay_channels = {channel.AboutNodeName: channel for channel in self._layout.DataChannels if channel.AboutNodeName in relay_node_names}
        relay_actor_configs = {config.ActorName: config for config in self._layout.I2cRelayComponent.ConfigList}
        
        for node_name in relay_node_names:
            if node_name in relay_actor_configs:
                config = relay_actor_configs[node_name]
                self._relay_configs[node_name] = {
                    "name": node_name,
                    "display_name": next((node.DisplayName for node in self._layout.ShNodes if node.Name == node_name), node_name),
                    "channel_name": relay_channels[node_name].Name,
                    "event_type": config.EventType,
                    "energizing_event": config.EnergizingEvent,
                    "de_energizing_event": config.DeEnergizingEvent,
                    "energized_state": config.EnergizedState,
                    "deenergized_state": config.DeEnergizedState,
                }
        
        # Create channel to relay mapping
        self._channel_to_relay = {
            relay_config["channel_name"]: relay_name
            for relay_name, relay_config in self._relay_configs.items()
        }
        
        print(f"DEBUG: Loaded {len(self._relay_configs)} relays")
        
        self._extract_thermostat_names()
        self._request_snapshot()
    
    def _process_snapshot(self, payload: bytes) -> None:
        """Process snapshot message"""
        print("DEBUG: Processing snapshot message")
        message = GWMessage[SnapshotSpaceheat].model_validate_json(payload)
        self._snapshot = message.Payload
        print(f"DEBUG: Snapshot loaded with {len(self._snapshot.LatestReadingList)} readings")
        
        self._extract_relay_states_from_snapshot()
        self._send_snapshot_to_clients()
    
    def _extract_relay_states_from_snapshot(self) -> None:
        """Extract relay states from snapshot data"""
        if not self._snapshot or not self._layout:
            return
            
        # Extract relay states from readings using existing channel mapping
        relay_states = {}
        for reading in self._snapshot.LatestReadingList:
            if reading.ChannelName in self._channel_to_relay:
                relay_name = self._channel_to_relay[reading.ChannelName]
                relay_states[relay_name] = {
                    "state": "energized" if reading.Value else "deenergized",
                    "time": reading.ScadaReadTimeUnixMs
                }
        
        # Update relay configs with states
        for relay_name, state_info in relay_states.items():
            if relay_name in self._relay_configs:
                self._relay_configs[relay_name]["state"] = state_info["state"]
                self._relay_configs[relay_name]["last_update"] = state_info["time"]
        
        print(f"DEBUG: Updated {len(relay_states)} relay states from snapshot")
    
    def _extract_thermostat_names(self) -> None:
        """Extract thermostat names from layout data"""
        if not self._layout:
            return
            
        thermostat_channel_name_pattern = re.compile(
            r"^zone(?P<zone_number>\d)-(?P<human_name>.*)-(temp|set|state)$"
        )
        
        thermostat_human_names = []
        for channel in self._layout.DataChannels:
            if match := thermostat_channel_name_pattern.match(channel.Name):
                if (human_name := match.group("human_name")) not in thermostat_human_names:
                    thermostat_human_names.append(human_name)
        
        self._thermostat_names = thermostat_human_names
        print(f"DEBUG: Extracted thermostat names: {self._thermostat_names}")
    
    def _send_snapshot_to_clients(self) -> None:
        """Send snapshot data to all WebSocket clients"""
        if not self._snapshot:
            print("DEBUG: No snapshot data available to send")
            return
            
        print(f"DEBUG: Sending snapshot to {len(self._websocket_clients)} clients")
        print(f"DEBUG: Snapshot has {len(self._snapshot.LatestReadingList)} readings")
        
        # Convert snapshot to dict for JSON serialization
        snapshot_data = {
            "type": "mqtt_message",
            "message_type": "snapshot.spaceheat",
            "payload": {
                "FromGNodeAlias": self._snapshot.FromGNodeAlias,
                "FromGNodeInstanceId": self._snapshot.FromGNodeInstanceId,
                "SnapshotTimeUnixMs": self._snapshot.SnapshotTimeUnixMs,
                "LatestReadingList": [
                    {
                        "ChannelName": reading.ChannelName,
                        "Value": reading.Value,
                        "ScadaReadTimeUnixMs": reading.ScadaReadTimeUnixMs
                    }
                    for reading in self._snapshot.LatestReadingList
                ],
                "LatestStateList": [
                    {
                        "MachineHandle": state.MachineHandle,
                        "StateEnum": state.StateEnum,
                        "State": state.State,
                        "UnixMs": state.UnixMs,
                        "Cause": state.Cause
                    }
                    for state in self._snapshot.LatestStateList
                ]
            }
        }
        
        message = json.dumps(snapshot_data)
        # print(f"DEBUG: Sending snapshot message: {message[:200]}...")
        
        # Store the message to be sent when clients connect or on next status update
        self._pending_snapshot_message = message
        print(f"DEBUG: Stored snapshot message for next client update")
    
    def _process_single_reading(self, payload: bytes) -> None:
        """Process single reading message to update relay states in real-time"""
        if not self._layout or not self._channel_to_relay:
            return
            
        try:
            message = GWMessage[SingleReading].model_validate_json(payload)
            reading = message.Payload
            
            if reading.ChannelName in self._channel_to_relay:
                relay_name = self._channel_to_relay[reading.ChannelName]
                new_state = "energized" if reading.Value else "deenergized"
                
                if relay_name in self._relay_configs:
                    old_state = self._relay_configs[relay_name].get("state", "unknown")
                    self._relay_configs[relay_name]["state"] = new_state
                    self._relay_configs[relay_name]["last_update"] = reading.ScadaReadTimeUnixMs
                    if old_state != new_state:
                        print(f"DEBUG: Relay {relay_name} changed from {old_state} to {new_state}")
                    
        except Exception as e:
            print(f"DEBUG: Error processing single reading: {e}")
            self.logger.exception(f"Error processing single reading: {e}")
    
    def _request_layout_lite(self) -> None:
        """Request layout from SCADA"""
        print("DEBUG: Requesting layout from SCADA")
        result = self._publish_message(
            SendLayout(
                FromGNodeAlias=H0N.admin,
                FromName=H0N.admin,
                ToName=H0N.primary_scada,
            )
        )
        print(f"DEBUG: Layout request result: {result}")
    
    def _request_snapshot(self) -> None:
        """Request snapshot from SCADA"""
        print("DEBUG: Requesting snapshot from SCADA")
        result = self._publish_message(SendSnap(FromGNodeAlias=H0N.admin))
        print(f"DEBUG: Snapshot request result: {result}")
    
    def _publish_message(self, payload) -> Result[MQTTMessageInfo, Exception | None]:
        """Publish message to MQTT broker"""
        message = GWMessage[type(payload)](
            Dst=self.settings.target_gnode,
            Src=H0N.admin,
            Payload=payload
        )
        topic = message.mqtt_topic()
        return self._mqtt_client.publish(
            topic,
            message.model_dump_json(indent=2).encode()
        )
    
    async def _start_control_timer(self, timeout_seconds: int, user_id: str):
        """Start a synchronized timer for all clients"""
        self._control_timeout = timeout_seconds
        self._control_start_time = time.time()
        self._current_controller = user_id
        
        # Cancel existing timer
        if self._timer_task:
            self._timer_task.cancel()
        
        # Start new timer
        self._timer_task = asyncio.create_task(self._timer_loop())
        
        # Broadcast timer start to all clients
        await self._broadcast_timer_update()
    
    async def _timer_loop(self):
        """Timer loop that broadcasts updates every second"""
        while True:
            try:
                await asyncio.sleep(1)
                await self._broadcast_timer_update()
            except asyncio.CancelledError:
                break
    
    async def _broadcast_timer_update(self):
        """Broadcast current timer state to all clients"""
        if self._control_timeout and self._control_start_time:
            elapsed = time.time() - self._control_start_time
            remaining = max(0, self._control_timeout - elapsed)
            
            if remaining <= 0:
                self._control_timeout = None
                self._control_start_time = None
                self._current_controller = None
                remaining = 0
                if self._timer_task:
                    self._timer_task.cancel()
                    self._timer_task = None
            
            await self._broadcast_to_websockets_async({
                "type": "timer_update",
                "time_remaining": remaining,
                "controller": self._current_controller
            })
    
    async def _broadcast_to_websockets_async(self, data: dict):
        if self._websocket_clients:
            message = json.dumps(data)
            for client in list(self._websocket_clients):
                try:
                    await client.send_str(message)
                except Exception as e:
                    self.logger.warning(f"Failed to send to WebSocket client: {e}")
                    self._websocket_clients.discard(client)
    
    async def handle_websocket_message(self, websocket: WebSocketResponse, message: str):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            ws_msg = WebSocketMessage(**data)
            
            if ws_msg.type == "relay_control":
                await self._handle_relay_control(ws_msg.data)
            elif ws_msg.type == "get_status":
                await self._send_status(websocket)
            elif ws_msg.type == "keepalive":
                await self._handle_keepalive(ws_msg.data)
            elif ws_msg.type == "release_control":
                await self._handle_release_control()
                
        except Exception as e:
            self.logger.exception(f"Error handling WebSocket message: {e}")
            await websocket.send_str(json.dumps({
                "type": "error",
                "message": str(e)
            }))
    
    async def _handle_relay_control(self, data: dict):
        """Handle relay control command"""
        relay_name = data.get("relay_name")
        timeout_seconds = data.get("timeout_seconds", 300)
        user_id = data.get("user_id", "unknown")
        
        if not relay_name:
            raise ValueError("Missing relay_name")
        
        # Find relay configuration
        if relay_name not in self._relay_configs:
            raise ValueError(f"Relay {relay_name} not found")
        
        # Get current relay state and toggle it
        current_state = self._relay_configs[relay_name].get("state", "unknown")
        relay_config = self._relay_configs[relay_name]
        
        if current_state == "energized":
            event_name = relay_config["de_energizing_event"]
            new_state = "deenergized"
        elif current_state == "deenergized":
            event_name = relay_config["energizing_event"]
            new_state = "energized"
        else:
            # Unknown state, default to de-energize
            event_name = relay_config["de_energizing_event"]
            new_state = "deenergized"
        
        print(f"DEBUG: Toggling relay {relay_name} from {current_state} to {new_state}")
        
        # Start/restart timer when relay is toggled
        await self._start_control_timer(timeout_seconds, user_id)
        
        event = FsmEvent(
            FromHandle=H0N.admin,
            ToHandle=f"{H0N.admin}.{relay_name}",
            EventType=relay_config["event_type"],
            EventName=event_name,
            SendTimeUnixMs=int(datetime.datetime.now().timestamp() * 1000),
            TriggerId=str(uuid.uuid4()),
        )
        
        # Send admin dispatch
        result = self._publish_message(
            AdminDispatch(
                DispatchTrigger=event,
                TimeoutSeconds=timeout_seconds
            )
        )
        
        if result.is_err():
            raise Exception(f"Failed to send relay command: {result.err()}")
        
        # Update our local variables with the new state
        self._relay_configs[relay_name]["state"] = new_state
        self._relay_configs[relay_name]["last_update"] = int(datetime.datetime.now().timestamp() * 1000)
        
        # Send updated status to all WebSocket clients
        await self._send_status_to_all_clients()
    
    async def _handle_keepalive(self, data: dict):
        """Handle keepalive command"""
        timeout_seconds = data.get("timeout_seconds")
        user_id = data.get("user_id", "unknown")
        await self._start_control_timer(timeout_seconds, user_id)
        
        # Send to SCADA
        result = self._publish_message(
            AdminKeepAlive(AdminTimeoutSeconds=timeout_seconds)
        )
        
        if result.is_err():
            raise Exception(f"Failed to send keepalive: {result.err()}")
        
        print(f"DEBUG: Keep alive sent by {user_id} for {timeout_seconds} seconds")
    
    async def _handle_release_control(self):
        """Handle release control command"""
        # Stop timer
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
        
        self._control_timeout = None
        self._control_start_time = None
        self._current_controller = None
        
        # Broadcast timer stop
        await self._broadcast_to_websockets_async({
            "type": "timer_update",
            "time_remaining": 0,
            "controller": None
        })
        
        # Send to SCADA
        result = self._publish_message(AdminReleaseControl())
        
        if result.is_err():
            raise Exception(f"Failed to send release control: {result.err()}")
        
        print("DEBUG: Release control sent")
        
        # Request a snapshot 1 second after release control to get updated relay states
        async def request_snapshot_after_delay():
            await asyncio.sleep(1.0)
            print("DEBUG: Requesting snapshot 1 second after release control")
            self._request_snapshot()
        
        # Start the delayed snapshot request
        asyncio.create_task(request_snapshot_after_delay())
    
    async def _send_status(self, websocket: WebSocketResponse):
        """Send current status to WebSocket client"""
        # Calculate current timer state
        time_remaining = 0
        if self._control_timeout and self._control_start_time:
            elapsed = time.time() - self._control_start_time
            time_remaining = max(0, self._control_timeout - elapsed)
        
        # Calculate last activity time
        last_activity_str = "Never"
        if self._last_activity_time:
            last_activity_str = f"{int(time.time() - self._last_activity_time)}s ago"
        
        status = {
            "type": "status",
            "mqtt_connected": self._mqtt_client.started() if self._mqtt_client else False,
            "relays": self._relay_configs,
            "layout_loaded": self._layout is not None,
            "snapshot_loaded": self._snapshot is not None,
            "time_remaining": time_remaining,
            "controller": self._current_controller,
            "target_gnode": self.settings.target_gnode,
            "messages_received": self._messages_received,
            "connected_clients": len(self._websocket_clients),
            "last_activity": last_activity_str,
            "relay_count": len(self._relay_configs),
            "thermostat_names": self._thermostat_names
        }
        # Status sent to web client
        await websocket.send_str(json.dumps(status))
        
        # Send snapshot data if available
        if self._pending_snapshot_message:
            try:
                await websocket.send_str(self._pending_snapshot_message)
                print(f"DEBUG: Sent pending snapshot to client")
            except Exception as e:
                self.logger.warning(f"Failed to send pending snapshot: {e}")
    
    async def _send_status_to_all_clients(self):
        """Send current status to all connected WebSocket clients"""
        # Calculate current timer state
        time_remaining = 0
        if self._control_timeout and self._control_start_time:
            elapsed = time.time() - self._control_start_time
            time_remaining = max(0, self._control_timeout - elapsed)
        
        # Calculate last activity time
        last_activity_str = "Never"
        if self._last_activity_time:
            last_activity_str = f"{int(time.time() - self._last_activity_time)}s ago"
        
        status = {
            "type": "status",
            "mqtt_connected": self._mqtt_client.started() if self._mqtt_client else False,
            "relays": self._relay_configs,
            "layout_loaded": self._layout is not None,
            "snapshot_loaded": self._snapshot is not None,
            "time_remaining": time_remaining,
            "controller": self._current_controller,
            "target_gnode": self.settings.target_gnode,
            "messages_received": self._messages_received,
            "connected_clients": len(self._websocket_clients),
            "last_activity": last_activity_str,
            "relay_count": len(self._relay_configs),
            "thermostat_names": self._thermostat_names
        }
        
        for client in list(self._websocket_clients):
            try:
                await client.send_str(json.dumps(status))
                
                # Send snapshot data if available
                if self._pending_snapshot_message:
                    try:
                        await client.send_str(self._pending_snapshot_message)
                        print(f"DEBUG: Sent pending snapshot to client")
                    except Exception as e:
                        self.logger.warning(f"Failed to send pending snapshot: {e}")
                        
            except Exception as e:
                self.logger.warning(f"Failed to send status to WebSocket client: {e}")
                self._websocket_clients.discard(client)
    
    async def websocket_handler(self, websocket: WebSocketResponse, path: str):
        """Handle WebSocket connections"""
        self._websocket_clients.add(websocket)
        self.logger.info(f"WebSocket client connected. Total clients: {len(self._websocket_clients)}")
        
        try:
            # Send initial status
            await self._send_status(websocket)
            
            # Handle messages
            async for msg in websocket:
                if msg.type == web.WSMsgType.TEXT:
                    await self.handle_websocket_message(websocket, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    self.logger.error(f'WebSocket error: {websocket.exception()}')
                elif msg.type == web.WSMsgType.CLOSE:
                    break
                
        except asyncio.CancelledError:
            self.logger.info("WebSocket connection cancelled")
            raise
        except Exception as e:
            self.logger.exception(f"WebSocket error: {e}")
        finally:
            self._websocket_clients.discard(websocket)
            self.logger.info(f"WebSocket client disconnected. Total clients: {len(self._websocket_clients)}")
    
    def start_mqtt(self):
        """Start MQTT client"""
        if not self._mqtt_client:
            self._setup_mqtt_client()
        self._mqtt_client.start()
    
    def stop_mqtt(self):
        """Stop MQTT client"""
        if self._mqtt_client:
            self._mqtt_client.stop()
    
    async def cleanup(self):
        """Clean up all resources"""
        # Cancel timer task if running
        if self._timer_task:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
            self._timer_task = None
        
        # Close all websocket connections
        for websocket in list(self._websocket_clients):
            try:
                await websocket.close()
            except Exception:
                pass  # Ignore errors during cleanup
        self._websocket_clients.clear()
        
        # Stop MQTT client
        self.stop_mqtt()
