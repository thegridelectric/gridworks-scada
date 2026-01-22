# actors/procedural/dist_pump_monitor.py

import time

from gwsproto.data_classes.house_0_names import H0CN


class DistPumpMonitor:
    """
    Diagnostic monitor for the distribution pump.

    Decides whether a recovery procedure should run based on:
      - zone calls
      - flow
      - zone-controller startup delay

    Owns diagnostic timing state but does not actuate.
    """
    ZONE_CONTROL_DELAY_SECONDS = 50
    THRESHOLD_FLOW_GPM_X100 = 50

    def __init__(self, *, host, doctor):
        self.host = host
        self.doctor = doctor

        # Diagnostic timing state
        self.zone_controller_triggered_at: float | None = None

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def needs_recovery(self) -> bool:
        """
        Return True if the distribution pump recovery procedure
        should be invoked.

        This method is side-effect-free with respect to actuation,
        but it *does* manage diagnostic state and doctor lifecycle.
        """
        h = self.host
        return True

        # --------------------------------------------------------
        # Guard: procedure already running
        # --------------------------------------------------------
        if self.doctor.running:
            h.log("[DistPumpCheck] Recovery already running; skipping check")
            return False

        # --------------------------------------------------------
        # Are any zones calling?
        # --------------------------------------------------------
        if not self._any_zones_calling():
            if self.zone_controller_triggered_at is not None:
                h.log("[DistPumpCheck] No zones calling; clearing trigger timer")
            self.zone_controller_triggered_at = None
            return False

        # --------------------------------------------------------
        # Do we have flow data?
        # --------------------------------------------------------
        flow_gpm_x100 = h.data.latest_channel_values.get(H0CN.dist_flow)
        if flow_gpm_x100 is None:
            h.log("[DistPumpCheck] Dist flow not found in latest channel values")
            return False

        # --------------------------------------------------------
        # Pump healthy → reset doctor + diagnostics
        # --------------------------------------------------------
        if flow_gpm_x100 > self.THRESHOLD_FLOW_GPM_X100:
            if self.zone_controller_triggered_at is not None:
                h.log(
                    "[DistPumpCheck] Pump running normally "
                    f"(GPM={flow_gpm_x100 / 100}); resetting state"
                )

            self.zone_controller_triggered_at = None
            self.doctor.reset()
            return False

        # --------------------------------------------------------
        # Pump OFF but zones calling → apply startup delay
        # --------------------------------------------------------
        # The distribution pump is downstream of a zone controller that:
        #   1) Opens zone valves first
        #   2) Waits for end-switch confirmation
        #   3) Only then enables the pump
        #
        # This introduces a normal startup delay (~30–40 seconds) during which
        # SCADA may observe "pump expected ON but no flow".
        #
        # We require the pump to remain OFF beyond this delay before triggering
        # pump_doctor, to avoid false recovery attempts during normal operation.
    
        now = time.monotonic()

        if self.zone_controller_triggered_at is None:
            self.zone_controller_triggered_at = now
            h.log(
                "[DistPumpCheck] Zone controller triggered; "
                "awaiting normal valve-open startup delay"
            )
            return False

        elapsed = now - self.zone_controller_triggered_at

        if elapsed <= self.ZONE_CONTROL_DELAY_SECONDS:
            h.log(
                "[DistPumpCheck] Waiting for zone controller startup "
                f"({int(elapsed)}s / {self.ZONE_CONTROL_DELAY_SECONDS}s)"
            )
            return False

        # --------------------------------------------------------
        # Startup delay exceeded → recovery warranted
        # --------------------------------------------------------
        h.log(
            "[DistPumpCheck] Startup delay exceeded "
            f"({int(elapsed)}s > {self.ZONE_CONTROL_DELAY_SECONDS}s); "
            "triggering pump doctor"
        )

        self.zone_controller_triggered_at = None
        return True

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _any_zones_calling(self) -> bool:
        h = self.host

        for i in h.h0cn.zone:
            whitewire_name = h.h0cn.zone[i].whitewire_pwr

            value = h.data.latest_channel_values.get(whitewire_name)
            if value is None:
                h.log(
                    f"[DistPumpCheck] {whitewire_name} missing from channel values"
                )
                continue

            if abs(value) > h.settings.whitewire_threshold_watts:
                return True

        return False
