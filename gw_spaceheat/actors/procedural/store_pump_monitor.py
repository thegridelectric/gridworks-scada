# actors/procedural/dist_pump_monitor.py

import time

from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.enums import StoreFlowRelay, RelayClosedOrOpen
from gwsproto.named_types import SingleMachineState

class StorePumpMonitor:
    """
    Diagnostic monitor for the store pump.

    Decides whether a recovery procedure should run based on:
      - store pump failsafe relay state
      - store flow
      - pump startup delay

    Owns diagnostic timing state but does not actuate.
    """
    PUMP_DELAY_SECONDS = 10
    THRESHOLD_FLOW_GPM_X100 = 50

    def __init__(self, *, host, doctor):
        self.host = host
        self.doctor = doctor

        # Diagnostic timing state
        self.pump_turned_on_s: float | None = None

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def needs_recovery(self) -> bool:
        """
        Return True if the store pump recovery procedure
        should be invoked.

        This method is side-effect-free with respect to actuation,
        but it *does* manage diagnostic state and doctor lifecycle.
        """
        h = self.host
        h.log("[StorePumpCheck] Starting")
        return True

        # --------------------------------------------------------
        # Guard: procedure already running
        # --------------------------------------------------------
        if self.doctor.running:
            h.log("[StorePumpCheck] Recovery already running; skipping check")
            return False

        # --------------------------------------------------------
        # Is the store pump failsafe relay closed?
        # --------------------------------------------------------

        charge_discharge_relay_state: SingleMachineState = h.data.latest_machine_state.get(h.store_charge_discharge_relay.name)
        store_pump_failsafe_relay_state: SingleMachineState = h.data.latest_machine_state.get(h.store_pump_failsafe.name)
        if not (
            charge_discharge_relay_state.State == StoreFlowRelay.DischargingStore
            and store_pump_failsafe_relay_state.State == RelayClosedOrOpen.RelayClosed
        ):
            h.log(f"[StorePumpCheck] Store pump is not discharging")
            h.log(charge_discharge_relay_state.State)
            h.log(store_pump_failsafe_relay_state.State)
            return False
        else:
            h.log(f"[StorePumpCheck] Store pump is discharging")
            h.log(charge_discharge_relay_state.State)
            h.log(store_pump_failsafe_relay_state.State)

        # --------------------------------------------------------
        # Do we have flow data?
        # --------------------------------------------------------
        flow_gpm_x100 = h.data.latest_channel_values.get(H0CN.store_flow)
        if flow_gpm_x100 is None:
            h.log("[StorePumpCheck] Store flow not found in latest channel values")
            return False

        # --------------------------------------------------------
        # Pump healthy → reset doctor + diagnostics
        # --------------------------------------------------------
        if flow_gpm_x100 > self.THRESHOLD_FLOW_GPM_X100:
            h.log(f"Latest GPM ({flow_gpm_x100/100}) is above threshold")
            if self.pump_turned_on_s is not None:
                h.log(
                    "[StorePumpCheck] Pump running normally "
                    f"(GPM={flow_gpm_x100 / 100}); resetting state"
                )

            self.pump_turned_on_s = None
            self.doctor.reset()
            return False
        else:
            h.log(f"Latest GPM ({flow_gpm_x100/100}) is not above threshold")

        # --------------------------------------------------------
        # No flow but relay state is discharging → apply startup delay
        # --------------------------------------------------------
        # The store pump and flow meter can have a startup delay during which
        # SCADA may observe "pump expected ON but no flow".
        #
        # We require the pump to remain OFF beyond this delay before triggering
        # pump_doctor, to avoid false recovery attempts during normal operation.
    
        now = time.monotonic()

        if self.pump_turned_on_s is None:
            self.pump_turned_on_s = now
            return False

        elapsed = now - self.pump_turned_on_s

        if elapsed <= self.PUMP_DELAY_SECONDS:
            h.log(
                "[StorePumpCheck] Waiting for pump startup "
                f"({int(elapsed)}s / {self.PUMP_DELAY_SECONDS}s)"
            )
            return False

        # --------------------------------------------------------
        # Startup delay exceeded → recovery warranted
        # --------------------------------------------------------
        h.log(
            "[StorePumpCheck] Startup delay exceeded "
            f"({int(elapsed)}s > {self.PUMP_DELAY_SECONDS}s); "
            "triggering pump doctor"
        )

        self.pump_turned_on_s = None
        return True
