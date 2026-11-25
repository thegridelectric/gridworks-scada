
import time
from typing import TYPE_CHECKING

from gwsproto.enums import CirculatorRole, LogLevel, StoreFlowRelay, RelayClosedOrOpen
from gwsproto.named_types import Glitch
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN

from actors.procedural.pump_power import is_running, meter_node_name, power_channel_name

if TYPE_CHECKING:
    from actors.procedural.procedural_host import ProceduralHost

class StorePumpMonitor:
    """
    Diagnostic monitor for the store pump.

    Decides whether a recovery procedure should run based on:
      - store pump relay state
      - store flow
      - store pump power: a pump drawing power is running, whatever the
        flow meter says, and a meter that reads no flow under a running
        pump gets a Warning glitch of its own
      - pump startup delay

    Owns diagnostic timing state but does not actuate.
    """
    PUMP_DELAY_SECONDS = 10
    THRESHOLD_FLOW_GPM_X100 = 50
    METER_SILENCE_SECONDS = 60

    def __init__(self, *, host: "ProceduralHost", doctor):
        self.host = host
        self.doctor = doctor
        self.power_channel = power_channel_name(host.layout, CirculatorRole.Store)

        # Diagnostic timing state
        self.pump_turned_on_s: float | None = None
        self.running_without_flow_s: float | None = None
        self.meter_warned = False

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

        # --------------------------------------------------------
        # Guard: procedure already running
        # --------------------------------------------------------
        if self.doctor.running:
            h.log("[StorePumpCheck] Recovery already running; skipping check")
            return False

        # --------------------------------------------------------
        # Is the store pump relay closed?
        # --------------------------------------------------------

        charge_discharge_relay_state = h.data.latest_machine_state.get(h.layout.store_charge_discharge_relay.name)
        pump_relay_state = h.data.latest_machine_state.get(h.layout.store_pump_relay.name)

        if pump_relay_state:
            if charge_discharge_relay_state:
                if (
                    charge_discharge_relay_state.State == StoreFlowRelay.ChargingStore
                    and pump_relay_state.State == RelayClosedOrOpen.RelayClosed
                ):
                    h.alert(summary="Store pump on and Charging Store!", details="This should never happen")
                    h.log("Store pump on and Charging Store! This should never happen")

            if pump_relay_state.State == RelayClosedOrOpen.RelayOpen:
                self.running_without_flow_s = None
                self.meter_warned = False
                return False
            
            h.log("[StorePumpCheck] Store pump relay is closed")
        else:
            h.log("[StorePumpCheck] Store pump relay not found")
            return False

        # --------------------------------------------------------
        # Do we have flow data?
        # --------------------------------------------------------
        flow_gpm_x100 = h.data.latest_channel_values.get(HCN.store_flow)
        if flow_gpm_x100 is None:
            h.log("[StorePumpCheck] Store flow not found in latest channel values")
            return False

        # --------------------------------------------------------
        # Pump healthy → reset doctor + diagnostics
        # --------------------------------------------------------
        if flow_gpm_x100 > self.THRESHOLD_FLOW_GPM_X100:
            if self.pump_turned_on_s is not None:
                h.log(
                    "[StorePumpCheck] Pump running normally "
                    f"(GPM={flow_gpm_x100 / 100}); resetting state"
                )

            self.pump_turned_on_s = None
            self.running_without_flow_s = None
            self.meter_warned = False
            self.doctor.reset()
            return False
        else:
            h.log(f"Latest GPM ({flow_gpm_x100/100}) is not above threshold")

        # --------------------------------------------------------
        # No flow but the pump draws power → the meter, not the pump
        # --------------------------------------------------------
        power_w = None
        if self.power_channel is not None:
            power_w = h.data.latest_channel_values.get(self.power_channel)
        if is_running(power_w):
            now = time.monotonic()
            if self.running_without_flow_s is None:
                self.running_without_flow_s = now
            elif (
                not self.meter_warned
                and now - self.running_without_flow_s > self.METER_SILENCE_SECONDS
            ):
                self.meter_warned = True
                h.log(
                    f"[StorePumpCheck] Store pump draws {power_w} W with "
                    f"GPM={flow_gpm_x100 / 100}: the flow meter reads zero under a running pump"
                )
                h._send_to(
                    h.ltn,
                    Glitch(
                        FromGNodeAlias=h.layout.scada_g_node_alias,
                        Node=meter_node_name(h.layout, HCN.store_flow),
                        Type=LogLevel.Warning,
                        Summary="Store flow meter reads zero under a running pump",
                        Details=(
                            f"{self.power_channel} {power_w} W, {HCN.store_flow} "
                            f"{flow_gpm_x100 / 100} gpm for over "
                            f"{self.METER_SILENCE_SECONDS} s; the pump is left running"
                        ),
                    ),
                )
            self.pump_turned_on_s = None
            return False
        self.running_without_flow_s = None

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
