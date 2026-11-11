import asyncio
import time
from typing import Sequence

from result import Ok, Err, Result

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from actors.sh_node_actor import ShNodeActor

from gwsproto.named_types import (
    I2cThermistorChannelConfig,
    SingleReading,
    SyncedReadings,
)
from gwsproto.data_classes.components import I2cThermistorReaderComponent
from gwsproto.property_format import SpaceheatName
from gwsproto.enums import TelemetryName

from plant import Heard, Streaks, ThermistorInput
from scada_app_interface import ScadaAppInterface
from thermistor_inputs import thermistor_channels


class I2cThermistorReader(ShNodeActor):

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)

        component = self.node.component

        if not isinstance(component, I2cThermistorReaderComponent):
            raise ValueError(
                f"{self.name} expected I2cThermistorComponent, got {type(component)}"
            )

        self.component: I2cThermistorReaderComponent = component
        self.cfgs = self.component.gt.ConfigList

        (
            self.device_configs,
            self.electrical_configs,
            self.electrical_cfg_by_device,
        ) = thermistor_channels(self.layout, self.node)

        self._stop_requested = False
        self._active_warning_keys: set[str] = set()
        self.streaks = Streaks()

        # Per-channel state
        self.latest_microvolts: dict[SpaceheatName, int] = {} # by electrical channel name
        self.latest_temp_c_x100: dict[SpaceheatName, int] = {} # by device channel name
        self.last_reported_temp_c_x100: dict[SpaceheatName, int] = {}

        self.adc = self.my_device(ThermistorInput)

    def _send_warning_once(self, key: str, summary: str, details: str = "") -> None:
        if key in self._active_warning_keys:
            return
        self._active_warning_keys.add(key)
        self.send_warning(summary=summary, details=details)

    def _clear_latest_reading(
        self,
        device_name: SpaceheatName,
        electrical_name: SpaceheatName,
    ) -> None:
        self.latest_temp_c_x100.pop(device_name, None)
        self.latest_microvolts.pop(electrical_name, None)

    def start(self):
        self.services.add_task(
            asyncio.create_task(self.main(), name=f"{self.name}-main")
        )
        self.log("I2cThermistorReader started")

    def stop(self) -> None:
        self._stop_requested = True

    async def join(self) -> None:
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        payload = message.Payload
        if self.adc.hears(payload) != Heard.NotMine:
            return Ok(True)
        return Err(
            ValueError(f"{self.name} received unexpected payload {type(payload)}")
        )

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, 120)]

    async def read_inputs(
        self, device_cfg: I2cThermistorChannelConfig
    ) -> tuple[bool, int | None, int | None]:
        """
        Input: device (i.e. temp) cfg 
        Returns:
          changed (based on temperature delta)
          microvolts
          temp_c_x100
        """
        
        device_name = device_cfg.ChannelName
        electrical_cfg = self.electrical_cfg_by_device[device_name]
        electrical_name = electrical_cfg.ChannelName
        device_ch = self.layout.data_channels[device_name]
        
        if device_ch.TelemetryName != TelemetryName.CelsiusTimes100:
            raise ValueError("requires a device channel (that reads CelsiusTimes100)")

        read = await self.adc.read(device_name)
        for said in self.streaks.fresh(device_name, read.said):
            self.send_warning(summary=said.summary, details=f"{device_name}: {said.details}")
        temp_c_x100 = read.temp_c_x100
        microvolts = read.microvolts
        if temp_c_x100 is None:
            self._clear_latest_reading(device_name, electrical_name)
            return False, None, None

        # --- change detection uses temperature ---
        if microvolts is None:
            self.latest_microvolts.pop(electrical_name, None)
        else:
            self.latest_microvolts[electrical_name] = microvolts
        self.latest_temp_c_x100[device_name] = temp_c_x100
        prev_temp = self.last_reported_temp_c_x100.get(device_name)
        if prev_temp is None:
            self.last_reported_temp_c_x100[device_name] = temp_c_x100
            return True, microvolts, temp_c_x100

        delta = abs(temp_c_x100 - prev_temp)
        threshold = self.layout.capture_tuning_by_channel[
            device_cfg.ChannelName
        ].AsyncCaptureDelta

        if threshold is None: # not reporting asynchronously
            changed = False
        else:
            changed = delta >= threshold
    
        if changed:
            self.last_reported_temp_c_x100[device_name] = temp_c_x100

        return changed, microvolts, temp_c_x100

    async def main(self):
        if not self.cfgs:
            self._send_warning_once(
                "i2c-thermistor-reader-no-config",
                "i2c-thermistor-reader-no-config",
                "",
            )
            return

        # assume uniform timing for now (first cfg)
        tuning0 = self.layout.capture_tuning_by_channel[self.cfgs[0].ChannelName]

        poll_period = (
            tuning0.PollPeriodMs / 1000.0
            if tuning0.PollPeriodMs
            else 1
        )

        period = tuning0.CapturePeriodS
        next_capture_ts = ((int(time.time()) // period) + 1) * period

        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            for device_cfg in self.device_configs.values():
                try:
                    changed, _, _ = await self.read_inputs(device_cfg)
                except Exception as e:
                    self._send_warning_once(
                        f"i2c-thermistor-loop-{device_cfg.ChannelName}",
                        "i2c-thermistor-read-failed",
                        f"{device_cfg.ChannelName}: {e}",
                    )
                    continue

                if changed:
                    try:
                        self._publish(device_cfg)
                    except Exception as e:
                        self._send_warning_once(
                            f"i2c-thermistor-publish-{device_cfg.ChannelName}",
                            "i2c-thermistor-publish-failed",
                            f"{device_cfg.ChannelName}: {e}",
                        )

            if time.time() >= next_capture_ts:
                try:
                    self._publish()
                except Exception as e:
                    self._send_warning_once(
                        "i2c-thermistor-periodic-publish-failed",
                        "i2c-thermistor-periodic-publish-failed",
                        str(e),
                    )
                now = time.time()
                while next_capture_ts <= now:
                    next_capture_ts += period

            sleep_s = min(poll_period, max(0, next_capture_ts - time.time()))
            await asyncio.sleep(sleep_s)

    def _publish(self, device_cfg: I2cThermistorChannelConfig | None = None):
        """
        If device_cfg is provided → publish that device channel (+ its electrical pair)
        If None → publish all device channels (+ electrical pairs)

        - Primary SCADA → SyncedReadings (temp + microvolts)
        - Derived Generator → SingleReading (temperature only)
        """

        if device_cfg is None:
            device_cfgs = self.device_configs.values()
        else:
            device_cfgs = [device_cfg]

        channel_name_list: list[SpaceheatName] = []
        value_list: list[int] = []

        now_ms = int(time.time() * 1000)

        for device_cfg in device_cfgs:
            device_name = device_cfg.ChannelName
            if device_name not in self.electrical_cfg_by_device:
                self._send_warning_once(
                    f"i2c-thermistor-publish-map-{device_name}",
                    "i2c-thermistor-publish-failed",
                    f"{device_name}: no electrical config mapped",
                )
                continue
            electrical_cfg = self.electrical_cfg_by_device[device_name]
            electrical_name = electrical_cfg.ChannelName

            # --- temperature ---
            if device_name not in self.latest_temp_c_x100:
                continue

            temp_val = self.latest_temp_c_x100[device_name]

            # add to SCADA bundle
            channel_name_list.append(device_name)
            value_list.append(temp_val)

            # send to derived generator (single reading, temperature only)
            if self.layout.feeds_derived([device_cfg.ChannelName]):
                self._send_to(
                    self.derived_generator,
                    SingleReading(
                        ChannelName=device_name,
                        Value=temp_val,
                        ScadaReadTimeUnixMs=now_ms,
                    ),
                )

            # --- microvolts (always to SCADA for now) ---
            if electrical_name in self.latest_microvolts:
                channel_name_list.append(electrical_name)
                value_list.append(self.latest_microvolts[electrical_name])

        if not channel_name_list:
            return

        # --- send to primary SCADA ---
        msg = SyncedReadings(
            ChannelNameList=channel_name_list,
            ValueList=value_list,
            ScadaReadTimeUnixMs=now_ms,
        )

        self._send_to(self.primary_scada, msg)
