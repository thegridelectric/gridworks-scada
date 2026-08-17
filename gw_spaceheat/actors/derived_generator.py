import time
import json
import pytz
import asyncio
import aiohttp
import math
import numpy as np
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Optional, Protocol, Sequence
from result import Ok, Result
from datetime import datetime,  timezone
from gwproto import Message

from gwsproto.data_classes.sh_node import ShNode
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage

from actors.sh_node_actor import ShNodeActor
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.conversions.temperature import convert_temp_to_f
from gwsproto.enums import (
    Unit, HeatCallInterpretation,
    ActuationAuthority, SeasonalStorageMode, ServiceMode, TelemetryName
)
from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.named_types import (
    Ha1Params, HeatingForecast, LinearOneDimensionalCalibration,
    RequiredEnergyLayered, ScadaParams,
    SingleReading, SyncedReadings,
    UsableEnergyLayered, WeatherForecast
)
from scada_app_interface import ScadaAppInterface


class SetpointPhase(StrEnum):
    Unknown = auto()
    LastHeatCallEndTemp = auto()
    SuspectZoneBelowSetpoint = auto()
    SuspectZoneAboveSetpoint = auto()


@dataclass
class SimpleFallingEdgeSetpointState:
    gw_temp_name: str
    heat_call_name: str
    phase: SetpointPhase = SetpointPhase.Unknown
    setpoint_f: float | None = None
    latest_gw_temp_f: float | None = None
    heat_call_active: bool | None = None
    last_emitted_setpoint_f: float = 1e9
    last_logged_phase: SetpointPhase | None = None


class DerivedHandler(Protocol):
    def __call__(
        self,
        dc: DerivedChannel,
        payload: SingleReading | None = None,
    ) -> None: ...

class DerivedGenerator(ShNodeActor):
    MAIN_LOOP_SLEEP_SECONDS = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False
        self.elec_assigned_amount = None
        self.previous_time = None
        self.received_new_params: bool = False
        self.last_evaluated_strategy = 0
        self.first_required_energy_update_done: bool = False

        # House parameters in the .env file
        self.is_simulated = self.settings.is_simulated
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.latitude = self.settings.latitude
        self.longitude = self.settings.longitude

        # used by the rswt quad params calculator
        self._cached_params: Optional[Ha1Params] = None 
        self._rswt_quadratic_params: Optional[np.ndarray] = None 
    
        self.log(f"self.timezone: {self.timezone}")
        self.log(f"self.latitude: {self.latitude}")
        self.log(f"self.longitude: {self.longitude}")
        self.log(f"Params: {self.params}")
        self.log(f"self.is_simulated: {self.is_simulated}")
        self.weather_forecast: Optional[WeatherForecast] = None
        self.coldest_oat_by_month = [-3, -7, 1, 21, 30, 31, 46, 47, 28, 24, 16, 0]

        self.strategy_handlers: dict[str, DerivedHandler] = {
            "identity": self.handle_identity,
            "affine": self.handle_affine,
            "sum": self.handle_sum,
            "heat-call": self.handle_heat_call,
            "simple-falling-edge-setpoint": self.handle_simple_falling_edge_setpoint,
            "system-model": self.handle_system_model,
        }

        self.derived_by_input: dict[str, list[DerivedChannel]] = {}
        self.system_models: list[DerivedChannel] = []
        self.simple_falling_edge_setpoint_states: dict[str, SimpleFallingEdgeSetpointState] = {}
        self.last_emitted: dict[str, int] = {}
        self.next_period_boundary_ts: dict[str, float] = {} # channel name, unix seconds
        self.next_phase_log_boundary_ts: dict[str, float] = {}
        self.init_derived_channels()

    def init_derived_channels(self) -> None:

        for dc in self.layout.derived_channels.values():

            if dc.CreatedByNodeName != self.name:
                continue
    
            handler = self.strategy_handlers.get(dc.Strategy)
            if handler is None:
                raise RuntimeError(
                    f"DerivedGenerator does not support strategy '{dc.Strategy}' "
                    f"(channel '{dc.Name}')"
                )

            if dc.InputChannelNames:
                for ch in dc.InputChannelNames:
                    self.derived_by_input.setdefault(ch, []).append(dc)
            else:
                self.system_models.append(dc)

            if dc.Strategy == "affine":
                params = dc.Parameters
                if params is None:
                    raise RuntimeError(
                        f"Affine DerivedChannel '{dc.Name}' is missing Parameters"
                    )
                try:
                    LinearOneDimensionalCalibration.model_validate(
                        params["Calibration"]
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"DerivedGenerator only supports "
                        f"linear.one.dimensional.calibration for affine channels. "
                        f"Channel '{dc.Name}' invalid: {e}"
                    )
                in_unit = self.layout.channel_registry.unit(dc.InputChannelNames[0])
                if in_unit is None:
                    raise RuntimeError(
                    f"No unit registered for input channel '{dc.InputChannelNames[0]}' "
                    f"(required by affine DerivedChannel '{dc.Name}')"
                )
                if in_unit not in [Unit.FahrenheitX100, 
                            TelemetryName.AirTempCTimes1000,
                            TelemetryName.WaterTempCTimes1000,
                            TelemetryName.AirTempFTimes1000,
                            TelemetryName.AirTempCTimes1000]:
                    raise RuntimeError("DerivedGenerator only handles temp-based affine conversions now")
                if dc.OutputUnit != Unit.FahrenheitX100:
                    raise RuntimeError(f"DerivedGenerator only handles affine conversions with output unit"
                                    f" FahrenheitX100, not {dc.OutputUnit}")
            elif dc.Strategy == "sum":
                if not dc.InputChannelNames:
                    raise RuntimeError(
                        f"Sum DerivedChannel '{dc.Name}' requires InputChannelNames"
                    )
                in_units = {
                    self.layout.channel_registry.unit(ch) for ch in dc.InputChannelNames
                }
                if None in in_units:
                    raise RuntimeError(
                        f"Sum DerivedChannel '{dc.Name}' has an input channel with no "
                        f"registered unit"
                    )
                if len(in_units) != 1:
                    raise RuntimeError(
                        f"Sum DerivedChannel '{dc.Name}' requires its inputs to share one "
                        f"unit (got {in_units}); summing differing units is undefined"
                    )
            elif dc.Strategy == "simple-falling-edge-setpoint":
                self.init_simple_falling_edge_setpoint_channel(dc)

        # 4) Final sanity check: every DerivedChannel must be reachable
        handled = set()
        for dcs in self.derived_by_input.values():
            handled.update(dcs)
        
        handled.update(self.system_models)
        handled_names = {dc.Name for dc in handled}
        expected = {
            dc.Name
            for dc in self.layout.derived_channels.values()
            if dc.CreatedByNodeName == self.name
        }

        missing = expected - handled_names
        if missing:
            raise RuntimeError(
                "DerivedGenerator has DerivedChannels it will never emit:\n"
                + "\n".join(missing)
            )

    def init_simple_falling_edge_setpoint_channel(self, dc: DerivedChannel) -> None:
        if dc.OutputUnit != Unit.FahrenheitX100:
            raise RuntimeError(
                f"Simple falling-edge setpoint channel '{dc.Name}' must use "
                f"OutputUnit FahrenheitX100, not {dc.OutputUnit}"
            )
        if len(dc.InputChannelNames) != 2:
            raise RuntimeError(
                f"Simple falling-edge setpoint channel '{dc.Name}' must declare "
                "exactly two InputChannelNames: [gw-temp, heat-call]"
            )

        gw_temp_name, heat_call_name = dc.InputChannelNames
        in_unit = self.layout.channel_registry.unit(gw_temp_name)
        if in_unit is None:
            raise RuntimeError(
                f"No unit registered for input channel '{gw_temp_name}' "
                f"(required by simple falling-edge setpoint channel '{dc.Name}')"
            )
        try:
            convert_temp_to_f(0, in_unit)
        except ValueError as e:
            raise RuntimeError(
                f"Simple falling-edge setpoint channel '{dc.Name}' requires a "
                f"temperature input, but '{gw_temp_name}' uses {in_unit}"
            ) from e

        heat_call_dc = self.layout.derived_channels.get(heat_call_name)
        if heat_call_dc is None or heat_call_dc.Strategy != "heat-call":
            raise RuntimeError(
                f"Simple falling-edge setpoint channel '{dc.Name}' requires a "
                f"heat-call DerivedChannel as its second input, not '{heat_call_name}'"
            )

        self.simple_falling_edge_setpoint_states[dc.Name] = SimpleFallingEdgeSetpointState(
            gw_temp_name=gw_temp_name,
            heat_call_name=heat_call_name,
        )
        self.log(f"Initialized simple falling-edge setpoint channel '{dc.Name}'")

    def handle_identity(self, dc: DerivedChannel, payload: SingleReading | None = None) -> None:
        """Returns the identical data, after unit transformation"""
        if payload is None:
            return

        in_unit = self.layout.channel_registry.unit(payload.ChannelName)
        assert in_unit

        temp_f = convert_temp_to_f(payload.Value, in_unit)

        if temp_f is None:
            return None

        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=dc.Name,
                Value=int(temp_f * 100),
                ScadaReadTimeUnixMs=payload.ScadaReadTimeUnixMs
            )
        )

    def handle_affine(self, dc: DerivedChannel, payload: SingleReading | None = None) -> None:
        """
        Apply a one-dimensional affine transformation to a single input reading.

        This handler:
        - Converts the raw input value to a physical float (based on input unit)
        - Applies y = M*x + B using LinearOneDimensionalCalibration
        - Converts the result to the DerivedChannel's OutputUnit
        - Emits a SingleReading for the derived channel

        Emission semantics are governed by dc.EmissionMethod (typically OnTrigger).
        """
        if payload is None:
            return

        assert dc.Parameters # enforced in axioms for DerivedChannelGt

        calib = LinearOneDimensionalCalibration.model_validate(
                dc.Parameters["Calibration"]
            )
        in_unit = self.layout.channel_registry.unit(payload.ChannelName)
        assert in_unit
        x = convert_temp_to_f(payload.Value, in_unit)

        if x is None:
            return

        # v001 calibration: B is an integer in the OutputUnit (FahrenheitX100)
        # scaling, so apply M to the FahrenheitX100-scaled input and add B there.
        assert dc.OutputUnit == Unit.FahrenheitX100
        temp_x100 = int(calib.M * (x * 100) + calib.B)
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=dc.Name,
                Value=temp_x100,
                ScadaReadTimeUnixMs=payload.ScadaReadTimeUnixMs
            )
        )

    def handle_sum(self, dc: DerivedChannel, payload: SingleReading | None = None) -> None:
        """Emit dc.Name = sum of the latest values of dc.InputChannelNames.

        Used for the derived primary-flow on a Siegenthaler-loop house (e.g. maple):
        primary-flow = sieg-send + sieg-flow. The handler fires when ANY input arrives
        (the channel is registered under each InputChannelName); it reads the fresh
        payload value plus the cached latest of the other inputs, and waits — emitting
        nothing — until every input has been seen at least once. Inputs and OutputUnit
        share one unit (enforced in init_derived_channels), so the sum is a straight
        integer add in that unit.
        """
        if payload is None:
            return
        total = 0
        for ch_name in dc.InputChannelNames:
            if ch_name == payload.ChannelName:
                value = payload.Value
            else:
                value = self.data.latest_channel_values.get(ch_name)
            if value is None:
                return  # not every input available yet
            total += value
        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=dc.Name,
                Value=total,
                ScadaReadTimeUnixMs=payload.ScadaReadTimeUnixMs,
            ),
        )

    @staticmethod
    def _next_period_boundary(now: float, period: int) -> float:
        return ((int(now) // period) + 1) * period

    def _advance_period_boundary(
        self,
        dc_name: str,
        now: float,
        period: int,
        boundaries: dict[str, float] | None = None,
    ) -> None:
        """Advance a channel's period boundary in whole `period` steps until it is
        in the future, so a gap in input readings yields one emission rather than
        a burst of catch-up emissions on subsequent readings."""
        if boundaries is None:
            boundaries = self.next_period_boundary_ts
        while boundaries[dc_name] <= now:
            boundaries[dc_name] += period

    def handle_heat_call(self, dc: DerivedChannel, payload: SingleReading | None = None) -> None:
        """
        Derive and emit a binary heat-call signal from a single raw input reading.

        The semantic interpretation of the raw value is determined by the
        HeatCallInterpretation enum declared in dc.Parameters["Interpretation"].

        Emits a SingleReading for the derived channel whenever an input reading
        is received. Logs transitions when the heat-call state changes.
        """
        if payload is None:
            return

        assert dc.Parameters is not None
        assert dc.EmitPeriodS is not None
        interp = HeatCallInterpretation(dc.Parameters.get("Interpretation"))
        threshold = dc.Parameters.get("Threshold")

        value = self.heat_call_value(payload.Value, interp, threshold)
        heat_call_reading = SingleReading(
            ChannelName=dc.Name,
            Value=value,
            ScadaReadTimeUnixMs=payload.ScadaReadTimeUnixMs,
        )
        
        now = time.time()
    
        last = self.last_emitted.get(dc.Name)
        changed = (last is None or value != last)

        # Periodic emission (boundary-aligned)
        period = dc.EmitPeriodS
        next_ts = self.next_period_boundary_ts.get(dc.Name)

        if next_ts is None:
            # First time seeing this channel → align to next boundary
            next_ts = self._next_period_boundary(now, period)
            self.next_period_boundary_ts[dc.Name] = next_ts

        periodic_due = now >= next_ts

        should_emit = changed or periodic_due

        if should_emit:
            self._send_to(
                self.primary_scada,
                heat_call_reading,
            )
            self.last_emitted[dc.Name] = value

            if periodic_due:
                self.log(
                    f"[HeatCall periodic] {dc.Name} "
                    f"now={round(now,1)} "
                    f"next={round(self.next_period_boundary_ts[dc.Name],1)} "
                    f"period={dc.EmitPeriodS}"
                )
                self._advance_period_boundary(dc.Name, now, period)

        self._dispatch_derived_input(heat_call_reading)

    def heat_call_value(
            self, 
            in_val: int,
            interpretation: HeatCallInterpretation,
            threshold: int | None = None) -> int:
        """
        Compute the binary heat-call state from a raw input value using a
        HeatCallInterpretation enum.

        Returns:
            1 → calling for heat
            0 → not calling for heat
        """
        match interpretation:
            case HeatCallInterpretation.DigitalZeroIsActive:
                return 1 if in_val == 0 else 0

            case HeatCallInterpretation.DigitalOneIsActive:
                return 1 if in_val == 1 else 0

            case HeatCallInterpretation.GreaterThanThreshold:
                if threshold is None: # should be prevented by axiom, guard anyway
                    return 0 
                return 1 if abs(in_val) > threshold else 0

            case _:
                return 0

    def _latest_gw_temp_f(self, gw_temp_name: str) -> float | None:
        in_unit = self.layout.channel_registry.unit(gw_temp_name)
        assert in_unit is not None
        raw = self.data.latest_channel_values.get(gw_temp_name)
        if raw is None:
            return None
        return convert_temp_to_f(raw, in_unit)

    def handle_simple_falling_edge_setpoint(self, dc: DerivedChannel, payload: SingleReading | None = None) -> None:
        """
        Derive a zone thermostat setpoint estimate from gw-temp and heat-call.

        The learned value is gw-temp at the falling edge of a heat call. Suspected
        manual setpoint changes are tracked in SetpointPhase without overwriting
        the last learned temperature on the wire.
        """
        if payload is None:
            return

        state = self.simple_falling_edge_setpoint_states[dc.Name]
        gw_temp_name = state.gw_temp_name
        heat_call_name = state.heat_call_name

        if payload.ChannelName not in {gw_temp_name, heat_call_name}:
            return

        assert dc.Parameters is not None
        setpoint_threshold_f = dc.Parameters["SetpointThresholdFX100"] / 100

        if payload.ChannelName == gw_temp_name:
            in_unit = self.layout.channel_registry.unit(payload.ChannelName)
            assert in_unit
            state.latest_gw_temp_f = convert_temp_to_f(payload.Value, in_unit)
        else:
            was_active = state.heat_call_active
            now_active = payload.Value >= 1
            state.heat_call_active = now_active
            # Heat call has just ended -> update the setpoint
            if was_active and not now_active:
                if state.latest_gw_temp_f is None:
                    state.latest_gw_temp_f = self._latest_gw_temp_f(gw_temp_name)
                if state.latest_gw_temp_f is not None:
                    state.setpoint_f = state.latest_gw_temp_f
                    state.phase = SetpointPhase.LastHeatCallEndTemp
                    self.log(f"Setpoint {dc.Name}: learned {state.setpoint_f} F at heat-call end")
                else:
                    self.log(f"Setpoint {dc.Name}: heat-call ended but no gw-temp available to learn setpoint")

        if state.heat_call_active is None:
            latest_heat_call = self.data.latest_channel_values.get(heat_call_name)
            if latest_heat_call is not None:
                state.heat_call_active = latest_heat_call >= 1

        if state.latest_gw_temp_f is None:
            state.latest_gw_temp_f = self._latest_gw_temp_f(gw_temp_name)

        # Suspected setpoint change
        if state.heat_call_active is not None and state.latest_gw_temp_f is not None:
            if state.setpoint_f is not None and state.phase == SetpointPhase.LastHeatCallEndTemp:
                if (
                    state.heat_call_active
                    and state.latest_gw_temp_f >= state.setpoint_f + setpoint_threshold_f
                ):
                    state.setpoint_f = None
                    state.phase = SetpointPhase.SuspectZoneBelowSetpoint
                elif (
                    not state.heat_call_active
                    and state.latest_gw_temp_f <= state.setpoint_f - setpoint_threshold_f
                ):
                    state.setpoint_f = None
                    state.phase = SetpointPhase.SuspectZoneAboveSetpoint
            
            elif state.phase == SetpointPhase.Unknown:
                if state.heat_call_active:
                    state.phase = SetpointPhase.SuspectZoneBelowSetpoint
                else:
                    state.phase = SetpointPhase.SuspectZoneAboveSetpoint

        phase_changed = state.phase != state.last_logged_phase

        assert dc.EmitPeriodS is not None
        period = dc.EmitPeriodS
        now = time.time()

        next_phase_log_ts = self.next_phase_log_boundary_ts.get(dc.Name)
        if next_phase_log_ts is None:
            next_phase_log_ts = self._next_period_boundary(now, period)
            self.next_phase_log_boundary_ts[dc.Name] = next_phase_log_ts

        phase_log_periodic_due = now >= next_phase_log_ts

        if phase_changed or phase_log_periodic_due:
            self.log(f"Setpoint {dc.Name}: phase={state.phase.name}")
            state.last_logged_phase = state.phase
            if phase_log_periodic_due:
                self._advance_period_boundary(dc.Name, now, period, self.next_phase_log_boundary_ts)

        if state.setpoint_f is None:
            return

        next_ts = self.next_period_boundary_ts.get(dc.Name)
        if next_ts is None:
            # First time seeing this channel → align to next boundary
            next_ts = self._next_period_boundary(now, period)
            self.next_period_boundary_ts[dc.Name] = next_ts

        periodic_due = now >= next_ts
        # AsyncEmitDelta is expressed in OutputUnit (FahrenheitX100); the
        # setpoint state is in whole degrees F, so scale the threshold by 100.
        async_emit_delta_f = dc.AsyncEmitDelta / 100
        changed = (
            abs(state.last_emitted_setpoint_f - state.setpoint_f)
            > async_emit_delta_f
        )
        should_emit = changed or periodic_due

        if should_emit:
            self.log(f"Setpoint {dc.Name}: {state.setpoint_f} F phase={state.phase}")
            self._send_to(
                self.primary_scada,
                SingleReading(
                    ChannelName=dc.Name,
                    Value=int(state.setpoint_f * 100),
                    ScadaReadTimeUnixMs=payload.ScadaReadTimeUnixMs,
                )
            )
            state.last_emitted_setpoint_f = state.setpoint_f
            if periodic_due:
                self._advance_period_boundary(dc.Name, now, period)

    def handle_system_model(
        self,
        dc: DerivedChannel,
        payload: SingleReading | None = None,
    ) -> None:
        """
        Evaluate and emit a DerivedChannel whose value is produced by a
        system-level energy model rather than a direct input reading.
        Currently supported models include:

            - gw0.usable.energy.layered
            - gw0.required.energy.layered

        System-model derived channels:
        - Have no InputChannelNames
        - Are evaluated opportunistically during the main loop
        - Depend on shared system state (e.g. temperatures, forecasts, settings)

        The specific computation performed is determined by the model declared
        in `dc.Parameters["Model"]`. This method:
        - Verifies the model is supported
        - Computes the value using the appropriate internal routine
        - Emits a SingleReading only when the value is well-defined

        If required inputs (e.g. buffer temperatures or heating forecast) are
        unavailable, the method returns silently and no data point is emitted.

        The DerivedGenerator will raise an exception at initialization time if
        it encounters a system-model DerivedChannel whose model it does not
        recognize or cannot handle.
        """
        params = dc.Parameters
        assert params is not None

        model = params["EnergyModel"]
        type_name = model.get("TypeName")
        if type_name == UsableEnergyLayered.type_name_value():
            value = self.compute_usable_energy_wh()

        elif type_name == RequiredEnergyLayered.type_name_value():
            value = self.compute_required_energy_wh()

        else:
            raise RuntimeError(
                f"Unsupported system model {type_name}"
            )

        if value is None:
            return

        self._send_to(
            self.primary_scada,
            SingleReading(
                ChannelName=dc.Name,
                Value=value,
                ScadaReadTimeUnixMs=int(time.time() * 1000),
            )
        )

    @property
    def params(self) -> Ha1Params:
        return self.data.ha1_params
    
    @property
    def no_power_rswt(self) -> float:
        alpha = self.params.AlphaTimes10 / 10
        beta = self.params.BetaTimes100 / 100
        return -alpha/beta

    @property
    def rswt_quadratic_params(self) -> np.ndarray:
        """Property to get quadratic parameters for calculating heating power 
        from required source water temp, recalculating if necessary
        """
        if self.params != self._cached_params:
            intermediate_rswt = self.params.IntermediateRswtF
            dd_rswt = self.params.DdRswtF
            intermediate_power = self.params.IntermediatePowerKw
            dd_power = self.params.DdPowerKw
            x_rswt = np.array([self.no_power_rswt, intermediate_rswt, dd_rswt])
            y_hpower = np.array([0, intermediate_power, dd_power])
            A = np.vstack([x_rswt**2, x_rswt, np.ones_like(x_rswt)]).T
            self._rswt_quadratic_params = np.linalg.solve(A, y_hpower)
            self._cached_params = self.params
            self.log(f"Calculating rswt_quadratic_params: {self._rswt_quadratic_params}")
        
        if self._rswt_quadratic_params is None:
            raise Exception("_rswt_quadratic_params should have been set here!!")
        return self._rswt_quadratic_params

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name="Derived Generator keepalive")
        )

    def stop(self) -> None:
        self._stop_requested = True
        
    async def join(self):
        ...

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]
    
    async def main(self):
        async with aiohttp.ClientSession() as session:
            await self.main_loop(session)

    async def main_loop(self, session: aiohttp.ClientSession) -> None:
        self.log("SynthGen about to get forecasts")
        await self.get_forecasts(session)
        await asyncio.sleep(2)
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))

            for dc in self.system_models:
                self.handle_system_model(dc)

            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src)
        if not from_node:
            return Ok(True) # or not?
        match message.Payload:
            case ScadaParams():
                self.log("Received new parameters, time to recompute forecasts!")
                self.received_new_params = True

            case SingleReading():
                self.handle_input_reading(from_node, message.Payload)

            case SyncedReadings():
                for ch, val in zip(
                message.Payload.ChannelNameList,
                        message.Payload.ValueList,
                    ):
                    self.handle_input_reading(
                        from_node,
                        SingleReading(
                            ChannelName=ch,
                            Value=val,
                            ScadaReadTimeUnixMs=message.Payload.ScadaReadTimeUnixMs,
                        ),
                    )
        return Ok(True)

    def _dispatch_derived_input(self, payload: SingleReading) -> None:
        derived_channels = self.derived_by_input.get(payload.ChannelName)
        if not derived_channels:
            return

        for dc in derived_channels:
            handler = self.strategy_handlers.get(dc.Strategy)
            if handler is None:
                raise RuntimeError(f"No handler for strategy {dc.Strategy} (dc={dc.Name})")
            handler(dc, payload)

    def handle_input_reading(self, from_node: ShNode, payload: SingleReading) -> None:
        self._dispatch_derived_input(payload)

    # Compute usable and required energy
    def compute_usable_energy_wh(self) -> int | None:
        """
        Computes the usable thermal energy (kWh) currently stored
        above the forecast-constrained return-water temperature.

        This method:
        - Simulates layer-by-layer discharge of tanks or buffer
        - Assumes stratified storage
        """
        if (
            self.ops.ActuationAuthority != ActuationAuthority.Active
            or self.ops.ServiceMode != ServiceMode.Heating
        ):
            return None

        if not self.buffer_temps_available:
            return None

        if self.heating_forecast is None:
            self.log("Skipping energy update: heating_forecast not yet available")
            return None

        latest_temps_f = self.latest_temps_f.copy()

        ordered_tank_layers = []
        if self.ops.SeasonalStorageMode== SeasonalStorageMode.AllTanks:
            for tank_idx in sorted(self.h0cn.tank):
                tank = self.h0cn.tank[tank_idx]
                ordered_tank_layers.extend([
                    tank.depth1,
                    tank.depth2,
                    tank.depth3,
                ])
        elif self.ops.SeasonalStorageMode== SeasonalStorageMode.BufferOnly: 
            ordered_tank_layers = [
                    H0CN.buffer.depth1,
                    H0CN.buffer.depth2,
                    H0CN.buffer.depth3,
                ]
        else:
            raise ValueError(f"Unsupported SeasonalStorageMode {self.ops.SeasonalStorageMode}")

        simulated_layers_f = [
            latest_temps_f[ch]
            for ch in ordered_tank_layers
            if ch in latest_temps_f
        ]

        if not simulated_layers_f:
            self.log("Usable energy not updated: no buffer/tank temperatures yet")
            return None

        gallons_per_layer = (
            self.GALLONS_PER_TANK * len(self.h0cn.tank)
        ) / len(simulated_layers_f)

        mass_kg_per_layer = gallons_per_layer * self.GALLON_PER_LITER

        usable_kwh = 0
        while True:
            hottest_f = simulated_layers_f[0]
            rwt_f =self.rwt_f(hottest_f)

            if rwt_f is None:
                return
            if round(hottest_f) == round(rwt_f):
                simulated_layers_f = [
                    sum(simulated_layers_f) / len(simulated_layers_f)
                ] * len(simulated_layers_f)

                if round(simulated_layers_f[0]) == round(rwt_f):
                    break

            delta_c = (hottest_f - rwt_f) * 5 / 9

            # add this layer's delta energy
            usable_kwh += (
                mass_kg_per_layer
                * self.WATER_SPECIFIC_HEAT_KWH_PER_KG_C # kWh needed to raise 1 liter 1 deg C
                * delta_c
            )
            # pop the layer
            simulated_layers_f = (
                simulated_layers_f[1:] + [rwt_f]
            )

        # self.log(f"Usable energy: {round(usable_kwh,1)} kWh")
        return int(usable_kwh * 1000)

    def evaluate_strategy(self):
        """
        Send an info Glitch if we think its time to change strategy
        """
        if self.ops.SeasonalStorageMode != SeasonalStorageMode.BufferOnly:
            return
        if time.time() - self.last_evaluated_strategy > 3600:
            self.last_evaluated_strategy = time.time()
        else:
            return
        simulated_layers = [self.params.MaxEwtF]*3   
        max_buffer_usable_kwh = 0
        while True:
            if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                simulated_layers = [sum(simulated_layers)/len(simulated_layers) for x in simulated_layers]
                if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                    break
            delta_t_celcius = (simulated_layers[0] - self.rwt_f(simulated_layers[0])) * 5/9
            max_buffer_usable_kwh += self.LITERS_PER_LAYER * self.WATER_SPECIFIC_HEAT_KWH_PER_KG_C * delta_t_celcius
            simulated_layers = simulated_layers[1:] + [self.rwt_f(simulated_layers[0])]          
        self.log(f"Max buffer usable energy: {round(max_buffer_usable_kwh,1)} kWh")
        required_energy = self.data.latest_channel_values.get(H0CN.required_energy, 0)
        if round(max_buffer_usable_kwh,1) < round(required_energy,1):
            summary = "Consider changing strategy to use all tanks and not just the buffer"
            details = f"A full buffer will not have enough energy to go through the next on-peak ({round(max_buffer_usable_kwh,1)}<{round(self.required_kwh,1)} kWh)"
            self.log(details)
            self.send_info(summary, details)
        
    def compute_required_energy_wh(self) -> int | None:
        """
        Computes  the required thermal energy (kWh) needed to
        cover upcoming on-peak periods, based on forecasted load and
        maximum usable storage.

        This method:
        - Requires forecasts to be present
        - Does not store state locally

        If forecasts are unavailable, returns None
        """
        required_kwh = 0
        time_now = datetime.now(self.timezone)

        if not self.buffer_temps_available:
            return None

        if self.heating_forecast is None:
            self.log("Not updating required energy until forecasts exist")
            return None

        forecasts_times_tz = [datetime.fromtimestamp(x, tz=self.timezone) for x in self.heating_forecast.Time]
        morning_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, self.heating_forecast.AvgPowerKw)
             if 7<=t.hour<=11]
            )
        midday_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, self.heating_forecast.AvgPowerKw)
             if 12<=t.hour<=15]
            )
        afternoon_kWh = sum(
            [kwh for t, kwh in zip(forecasts_times_tz, self.heating_forecast.AvgPowerKw)
             if 16<=t.hour<=19]
            )
        # Find the maximum storage
        if self.ops.SeasonalStorageMode == SeasonalStorageMode.AllTanks:
            num_layers = len(self.h0cn.tank) * self.NUM_LAYERS_PER_TANK
        elif self.ops.SeasonalStorageMode == SeasonalStorageMode.BufferOnly:
            num_layers = self.NUM_LAYERS_PER_TANK # just the buffer
        else:
            raise Exception(f"not prepared for seasonal storage mode {self.ops.SeasonalStorageMode}")

        simulated_layers = [self.params.MaxEwtF + 10] * num_layers
        max_storage_kwh = 0
        while True:
            if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                simulated_layers = [sum(simulated_layers)/len(simulated_layers) for x in simulated_layers]
                if round(self.rwt_f(simulated_layers[0])) == round(simulated_layers[0]):
                    break

            delta_t_celcius = (simulated_layers[0] - self.rwt_f(simulated_layers[0])) * 5/9
            max_storage_kwh += self.LITERS_PER_LAYER * self.WATER_SPECIFIC_HEAT_KWH_PER_KG_C * delta_t_celcius
            simulated_layers = simulated_layers[1:] + [self.rwt_f(simulated_layers[0])]
        if (((time_now.weekday()<4 or time_now.weekday()==6) and time_now.hour>=20) or (time_now.weekday()<5 and time_now.hour<=6)):
            self.log('Preparing for a morning onpeak + afternoon onpeak')
            weather_forecasts_times_tz = [datetime.fromtimestamp(x, tz=self.timezone) for x in self.weather_forecast.Time]
            midday_oat = min([
                oat for t, oat in zip(weather_forecasts_times_tz, self.weather_forecast.OatF)
                if 12<=t.hour<=15
            ])
            midday_cop = self.params.CopMin if midday_oat<self.params.CopMinOatF else self.params.CopIntercept + self.params.CopOatCoeff*midday_oat
            afternoon_missing_kWh = afternoon_kWh - (0.8*4*self.params.HpMaxKwEl*midday_cop - midday_kWh) # assume 80% of max power (defrosts, turn on)
            if afternoon_missing_kWh<0:
                required = morning_kWh
            else:
                required = morning_kWh + afternoon_missing_kWh
            required_kwh = min(required, max_storage_kwh)
        elif (time_now.weekday()<5 and time_now.hour>=12 and time_now.hour<16):
            self.log('Preparing for an afternoon onpeak')
            required_kwh = afternoon_kWh
        else:
            self.log("Currently in on-peak or no on-peak period coming up soon")
        
        return int(required_kwh * 1000)

    def delta_T(self, swt: float) -> float:
        a, b, c = self.rswt_quadratic_params
        delivered_heat_power = a*swt**2 + b*swt + c
        dd_delta_t = self.params.DdDeltaTF
        dd_power = self.params.DdPowerKw
        d = dd_delta_t/dd_power * delivered_heat_power
        return d if d>0 else 0
        
    def required_heating_power(self, oat: float, wind_speed_mph: float) -> float:
        ws = wind_speed_mph
        alpha = self.params.AlphaTimes10 / 10
        beta = self.params.BetaTimes100 / 100
        gamma = self.params.GammaEx6 / 1e6
        r = alpha + beta*oat + gamma*ws*(65-oat)
        r = r * (1 + self.ops.LoadOverestimationPercent/100)
        return round(r,2) if r>0 else 0

    def required_swt(self, required_kw_thermal: float) -> float:
        a, b, c = self.rswt_quadratic_params
        c2 = c - required_kw_thermal
        return round((-b + (b**2-4*a*c2)**0.5)/(2*a), 2)
    
    async def get_weather(self, session: aiohttp.ClientSession) -> None:
        config_dir = self.settings.paths.config_dir
        weather_file = config_dir / "weather.json"
        try:
            url = f"https://api.weather.gov/points/{self.latitude},{self.longitude}"
            response = await session.get(url)
            if response.status != 200:
                self.log(f"Error fetching weather forecast url: {response.status}")
                raise Exception()
            
            data = await response.json()
            forecast_hourly_url = data['properties']['forecastHourly']
            forecast_response = await session.get(forecast_hourly_url)
            if forecast_response.status != 200:
                self.log(f"Error fetching hourly weather forecast: {forecast_response.status}")
                raise Exception()
            
            forecast_data = await forecast_response.json()
            forecasts_all = {
                datetime.fromisoformat(period['startTime']): 
                period['temperature']
                for period in forecast_data['properties']['periods']
                if 'temperature' in period and 'startTime' in period 
                and datetime.fromisoformat(period['startTime']) > datetime.now(tz=self.timezone)
            }
            ws_forecasts_all = {
                datetime.fromisoformat(period['startTime']): 
                int(period['windSpeed'].replace(' mph',''))
                for period in forecast_data['properties']['periods']
                if 'windSpeed' in period and 'startTime' in period 
                and datetime.fromisoformat(period['startTime']) > datetime.now(tz=self.timezone)
            }
            forecasts_48h = dict(list(forecasts_all.items())[:48])
            ws_forecasts_48h = dict(list(ws_forecasts_all.items())[:48])
            weather = {
                'time': [int(x.astimezone(timezone.utc).timestamp()) for x in list(forecasts_48h.keys())],
                'oat': list(forecasts_48h.values()),
                'ws': list(ws_forecasts_48h.values())
                }
            self.log(f"Obtained a {len(forecasts_all)}-hour weather forecast starting at {weather['time'][0]}")

            # Save 96h weather forecast to a local file
            forecasts_96h = dict(list(forecasts_all.items())[:96])
            ws_forecasts_96h = dict(list(ws_forecasts_all.items())[:96])
            weather_96h = {
                'time': [int(x.astimezone(timezone.utc).timestamp()) for x in list(forecasts_96h.keys())],
                'oat': list(forecasts_96h.values()),
                'ws': list(ws_forecasts_96h.values()),
                }
            with open(weather_file, 'w') as f:
                json.dump(weather_96h, f, indent=4) 
        
        except Exception as e:
            self.log(f"[!] Unable to get weather forecast from API: {e}")
            try:
                # Try reading an old forecast from local file
                with open(weather_file, 'r') as f:
                    weather_96h = json.load(f)
                    self.weather_96h = weather_96h
                if weather_96h['time'][-1] >= time.time()+ 48*3600:
                    self.log("A valid weather forecast is available locally.")
                    seconds_late = time.time() - weather_96h['time'][0]
                    hours_late = math.ceil(seconds_late/3600)
                    weather = {}
                    for key in weather_96h:
                        weather[key] = weather_96h[key][hours_late:hours_late+48]
                    self.first_time = weather['time'][0]
                    if weather['oat'] == []:
                        raise Exception()
                    if weather['time'][0] < time.time():
                        raise Exception(f"Weather forecast start of {weather['time'][0]} is in the past!! Check math")
                else:
                    self.log("No valid weather forecasts available locally. Using coldest of the current month.")
                    current_month = datetime.now().month-1
                    weather = {
                        'time': [int(time.time()+(1+x)*3600) for x in range(48)],
                        'oat': [self.coldest_oat_by_month[current_month]]*48,
                        'ws': [0]*48,
                        }
            except Exception as e:
                self.log(f"Issue getting local weather forecast! Using coldest of the current month.\n Issue: {e}")
                current_month = datetime.now().month-1
                weather = {
                    'time': [int(time.time()+(1+x)*3600) for x in range(48)],
                    'oat': [self.coldest_oat_by_month[current_month]]*48,
                    'ws': [0]*48,
                    }
        # International Civil Aviation Organization: 4-char alphanumeric code
        # assigned to airports and weather observation stations
        ICAO_CODE = "KMLT"
        WEATHER_CHANNEL = f"weather.gov.{ICAO_CODE}".lower()

        self.weather_forecast = WeatherForecast(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            WeatherChannelName=WEATHER_CHANNEL,
            Time = weather['time'],
            OatF = weather['oat'],
            WindSpeedMph= weather['ws'],
        )

    async def get_forecasts(self, session: aiohttp.ClientSession):
    
        await self.get_weather(session)
        if self.weather_forecast is None:
            self.log("No weather forecast available. Could not compute heating forecasts.")
            return
        
        forecasts = {}
        forecasts['time'] = self.weather_forecast.Time
        forecasts['avg_power'] = [
            self.required_heating_power(oat, ws) 
            for oat, ws in zip(self.weather_forecast.OatF, self.weather_forecast.WindSpeedMph)]
        forecasts['required_swt'] = [self.required_swt(x) for x in forecasts['avg_power']]
        forecasts['required_swt_delta_T'] = [round(self.delta_T(x),2) for x in forecasts['required_swt']]

        # Send cropped 24-hour heating forecast to aa & ha for their own use
        # and send both the 48-hour weather forecast and 24-hr heating forecast to Ltn for record-keeping
        hf = HeatingForecast(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            Time = forecasts['time'][:24],
            AvgPowerKw = forecasts['avg_power'][:24],
            RswtF = forecasts['required_swt'][:24],
            RswtDeltaTF = forecasts['required_swt_delta_T'][:24],
            WeatherUid=self.weather_forecast.WeatherUid
        )

        # Ensure energy state is up-to-date before publishing forecast;
        # downstream actors treat the forecast as a trigger, not as state.
        self.data.heating_forecast = hf
        self._send_to(self.ltn, hf)
        self._send_to(self.ltn, self.weather_forecast)

        if not self.first_required_energy_update_done:
            self.log("Updating usable and required energy")
            self.compute_usable_energy_wh()
            self.compute_required_energy_wh()
            self.first_required_energy_update_done = True

        forecast_start = datetime.fromtimestamp(self.weather_forecast.Time[0], tz=self.timezone)
        self.log(f"Got forecast starting {forecast_start.strftime('%Y-%m-%d %H:%M:%S')}")

    def rwt_f(self, swt_f: float) -> float:
        """
        Returns the forecast-constrained return water temperature for a given
        source (leaving) water temperature.

        This function models how much heat can be extracted from water at temperature
        `swt_f` while attempting to meet the forecasted load:

        - If `swt_f` is well below the required SWT, no heat can be extracted
        and return temperature equals supply temperature.
        - If `swt_f` is near the required SWT, partial extraction is possible
        with a reduced delta-T.
        - If `swt_f` is above the required SWT, full extraction is assumed.

        NOTE:
        This is not "the return water temperature at required SWT".
        It is a load- and forecast-limited effective return temperature.
        Requires self.heating_forecast
        """
        if self.heating_forecast is None:
            raise RuntimeError(
                "rwt_f called before heating_forecast is available"
            )
        forecasts_times_tz = [datetime.fromtimestamp(x, tz=self.timezone) for x in self.heating_forecast.Time]
        timenow = datetime.now(self.timezone)
        if timenow.hour > 19 or timenow.hour < 12:
            required_swt = max(
                [rswt for t, rswt in zip(forecasts_times_tz, self.heating_forecast.RswtF)
                if t.hour in [7,8,9,10,11,16,17,18,19]]
                )
        else:
            required_swt = max(
                [rswt for t, rswt in zip(forecasts_times_tz, self.heating_forecast.RswtF)
                if t.hour in [16,17,18,19]]
                )
        if swt_f < required_swt - 10:
            delta_t = 0
        elif swt_f < required_swt:
            delta_t = self.delta_T(required_swt) * (swt_f-(required_swt-10))/10
        else:
            delta_t = self.delta_T(swt_f)
        return round(swt_f - delta_t,2)
