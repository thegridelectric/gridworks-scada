import time
from datetime import datetime
from typing import Optional

from actors.local_control.tou_base import LocalControlTouBase
from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.enums import (
   LocalControlBufferOnlyState, LocalControlBufferOnlyEvent, LocalControlTopState,
   SeasonalStorageMode
)
from gwsproto.named_types import SingleMachineState
from transitions import Machine

from scada_app_interface import ScadaAppInterface


class BufferOnlyTouLocalControl(LocalControlTouBase):
    states = LocalControlBufferOnlyState.values()

    transitions = (
        [
            # Initializing
            {"trigger": "BufferNeedsCharge", "source": "Initializing", "dest": "HpOn"},
            {"trigger": "BufferFull", "source": "Initializing", "dest": "HpOff"},
            {"trigger": "OnPeakStart", "source": "Initializing", "dest": "HpOff"},
            # Starting at: HP on, Store off ============= HP -> buffer
            {"trigger": "BufferFull", "source": "HpOn", "dest": "HpOff"},
            {"trigger": "OnPeakStart", "source": "HpOn", "dest": "HpOff"},
            # Starting at: HP off, Store off ============ idle
            {"trigger": "BufferNeedsCharge", "source": "HpOff", "dest": "HpOn"},
        ]
        + [
            {"trigger": "GoDormant", "source": state, "dest": "Dormant"}
            for state in states
            if state != "Dormant"
        ]
        + [{"trigger": "WakeUp", "source": "Dormant", "dest": "Initializing"}]
    )

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        if self.settings.seasonal_storage_mode != SeasonalStorageMode.BufferOnly:
            raise Exception(
                f"Expect BufferOnly Local Control Strategy, got {self.settings.seasonal_storage_mode}"
            )

        self.buffer_declared_ready = False
        self.time_hp_turned_on = None
        self.full_buffer_energy: Optional[float] = None  # in kWh

        self.machine = Machine(
            model=self,
            states=BufferOnlyTouLocalControl.states,
            transitions=BufferOnlyTouLocalControl.transitions,
            initial=LocalControlBufferOnlyState.Initializing,
            send_event=True,
        )
        self.state: LocalControlBufferOnlyState = LocalControlBufferOnlyState.Initializing
        self.log("STARTING BufferOnly LocalControl")

    def trigger_normal_event(self, event: LocalControlBufferOnlyEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.state

        if event == LocalControlBufferOnlyEvent.OnPeakStart:
            self.OnPeakStart()
        elif event == LocalControlBufferOnlyEvent.BufferFull:
            self.BufferFull()
        elif event == LocalControlBufferOnlyEvent.BufferNeedsCharge:
            self.BufferNeedsCharge()
        elif event == LocalControlBufferOnlyEvent.TemperaturesAvailable:
            self.TemperaturesAvailable()
        elif event == LocalControlBufferOnlyEvent.GoDormant:
            self.GoDormant()
        elif event == LocalControlBufferOnlyEvent.WakeUp:
            self.WakeUp()
        else:
            raise Exception(f"Do not know event {event}")

        self.log(f"{event}: {orig_state} -> {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.normal_node.handle,
                StateEnum=LocalControlBufferOnlyState.enum_name(),
                State=self.state,
                UnixMs=now_ms,
                Cause=event,
            ),
        )

    def time_to_trigger_system_cold(self) -> bool:
        """
        Logic for triggering SystemCold (and moving to top state UsingNonElectricBackup).
        In shoulder, this means: 1) house is cold 2) buffer is really empty
        """
        return self.is_system_cold() and self.is_buffer_empty()

    def normal_node_state(self) -> str:
        return self.state

    def is_initializing(self) -> bool:
        return self.state == LocalControlBufferOnlyState.Initializing

    def normal_node_goes_dormant(self) -> None:
        """Trigger GoDormant event"""
        if self.state != LocalControlBufferOnlyState.Dormant:
            self.trigger_normal_event(LocalControlBufferOnlyEvent.GoDormant)

    def normal_node_wakes_up(self) -> None:
        """WakeUp: Dormant -> Initializing for self.state and
        then engage brain"""
        if self.state == LocalControlBufferOnlyState.Dormant:
            self.trigger_normal_event(LocalControlBufferOnlyEvent.WakeUp)
            self.time_since_blind = None
            self.engage_brain()

    def engage_brain(self) -> None:
        """
        Manages the logic for the Normal top state, (ie. self.state)
        """
        if self.top_state != LocalControlTopState.Normal:
            self.log(f"brain is only for Normal top state, not {self.top_state}")
            return

        if self.state == LocalControlBufferOnlyState.Dormant:
            self.alert("Bad LocalControl State", "TopState Normal, state Dormant!")
            self.trigger_normal_event(LocalControlBufferOnlyEvent.WakeUp)

        if not self.actuators_initialized:
            self.initialize_actuators()

        previous_state = self.state

        if self.is_onpeak():
            self.buffer_declared_ready = False
            self.full_buffer_energy = None

        if not (self.heating_forecast and self.buffer_temps_available):
            if self.time_since_blind is None:
                self.time_since_blind = time.time()
            elif time.time() - self.time_since_blind > self.BLIND_MINUTES * 60:
                self.log("Scada is missing forecasts and/or critical temperatures since at least 5 min.")
                self.log("Moving into ScadaBlind top state")
                self.trigger_missing_data()
            elif self.time_since_blind is not None:
                self.log(
                    f"Blind since {int(time.time() - self.time_since_blind)} seconds"
                )
        else:
            if self.time_since_blind is not None:
                self.time_since_blind = None

            if self.state == LocalControlBufferOnlyState.Initializing:
                if self.buffer_temps_available and self.data.channel_has_value(H0CN.required_energy):
                    if self.is_onpeak():
                        self.trigger_normal_event(LocalControlBufferOnlyEvent.OnPeakStart)
                    else:
                        if self.is_buffer_empty() or not self.is_buffer_ready():
                            self.trigger_normal_event(LocalControlBufferOnlyEvent.BufferNeedsCharge)
                        else:
                            self.trigger_normal_event(LocalControlBufferOnlyEvent.BufferFull)

            elif self.state == LocalControlBufferOnlyState.HpOn:
                if self.is_onpeak():
                    self.trigger_normal_event(LocalControlBufferOnlyEvent.OnPeakStart)
                elif self.is_buffer_full() and self.is_buffer_ready():
                    self.trigger_normal_event(LocalControlBufferOnlyEvent.BufferFull)

            elif self.state == LocalControlBufferOnlyState.HpOff:
                if not self.is_onpeak():
                    if self.is_buffer_empty():
                        self.trigger_normal_event(LocalControlBufferOnlyEvent.BufferNeedsCharge)
                    elif not self.is_buffer_ready():

                        if self.buffer_declared_ready:
                            if self.full_buffer_energy is None:
                                if self.usable_kwh < 0.9 * self.required_kwh:
                                    self.trigger_normal_event(LocalControlBufferOnlyEvent.BufferNeedsCharge)
                            else:
                                if self.usable_kwh < 0.7 * self.full_buffer_energy:
                                    self.trigger_normal_event(LocalControlBufferOnlyEvent.BufferNeedsCharge)
                        else:
                            self.trigger_normal_event(LocalControlBufferOnlyEvent.BufferNeedsCharge)

        if (
            self.state != previous_state
        ) and self.top_state == LocalControlTopState.Normal:
            self.update_relays(previous_state)

    def update_relays(self, previous_state) -> None:
        if self.top_state != LocalControlTopState.Normal:
            raise Exception("Can not go into update_relays if top state is not Normal")
        if (
            self.state == LocalControlBufferOnlyState.Dormant
            or self.state == LocalControlBufferOnlyState.Initializing
        ):
            return
        if (
            previous_state != LocalControlBufferOnlyState.HpOn
            and self.state == LocalControlBufferOnlyState.HpOn
        ):
            self.turn_on_HP(from_node=self.normal_node)
            self.time_hp_turned_on = time.time()
        if (
            previous_state != LocalControlBufferOnlyState.HpOff
            and self.state == LocalControlBufferOnlyState.HpOff
        ):
            self.turn_off_HP(from_node=self.normal_node)
            self.time_hp_turned_on = None

    def is_buffer_ready(self) -> bool:
        if datetime.now(self.timezone).hour not in [5, 6] + [14, 15]: # TODO: centralize TOU hour definition
            self.log("No onpeak period coming up soon.")
            self.buffer_declared_ready = False
            return True

        # Add the requirement of getting to the start of onpeak
        now = datetime.now(self.timezone)
        onpeak_duration_hours = 5 if now.hour in [5, 6] else 4
        onpeak_start_hour = 7 if now.hour in [5, 6] else 16
        onpeak_start_time = self.timezone.localize(
            datetime(now.year, now.month, now.day, onpeak_start_hour, 0)
        )
        time_to_onpeak = onpeak_start_time - now
        hours_to_onpeak = round(time_to_onpeak.total_seconds() / 3600, 2)
        self.log(f"There are {hours_to_onpeak} hours left to the start of onpeak")
        required_buffer_energy = self.required_kwh * (
            1 + hours_to_onpeak / onpeak_duration_hours
        )

        if self.usable_kwh >= required_buffer_energy:
            self.log(
                f"Buffer ready for onpeak (usable {round(self.usable_kwh)} kWh >= required {round(required_buffer_energy,1)} kWh)"
            )
            self.buffer_declared_ready = True
            return True
        else:
            if H0N.buffer_cold_pipe in self.latest_temps_f:
                self.log(f"Buffer cold pipe: {self.latest_temps_f[H0N.buffer_cold_pipe]} F")
                if (self.latest_temps_f[H0N.buffer_cold_pipe] > self.params.MaxEwtF):
                    self.log(f"The buffer is not ready, but the bottom is above the maximum EWT ({self.params.MaxEwtF} F).")
                    self.log("The buffer will therefore be considered ready, as we cannot charge it further.")
                    self.full_buffer_energy = self.usable_kwh
                    self.buffer_declared_ready = True
                    return True
            self.log(f"Buffer not ready for onpeak (usable {round(self.usable_kwh,1)} kWh < required {round(required_buffer_energy,1)} kWh)")
            return False
