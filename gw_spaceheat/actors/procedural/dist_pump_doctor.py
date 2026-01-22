import uuid
import time
from gwproto import Message
from gwsproto.enums import LogLevel
from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.named_types import AnalogDispatch, Glitch

class DistPumpDoctor:
    """
    Procedural, non-transactive recovery for distribution pump failures.
    See actors.procedural for architectural constraints.
    """
    MAX_PUMP_DOCTOR_ATTEMPTS = 3
    MAX_WAIT_SECONDS = 60
    THRESHOLD_FLOW_GPM_X100 = 50

    def __init__(self, host: "LocalControlTouBase"):
        self.host = host
        self.running = False
        self.attempts = 0
        self.exhausted = False

    def reset(self) -> None:
        """Clear attempts and exhaustion state when pump health is restored."""
        self.attempts = 0
        self.exhausted = False


    async def run(self) -> None:
        h = self.host
        try:
            try:
                h_node = self.host.normal_node
            except:
                h_node = self.host.node
        except Exception as e:
            h.log(f"[DistPumpDoctor] Could not find host node: {e}")
            return

        if self.running:
            h.log("[DistPumpDoctor] Already running, skipping")
            return

        self.running = True
        try:
            if self.attempts >= self.MAX_PUMP_DOCTOR_ATTEMPTS:
                if self.exhausted:
                    return

                self.exhausted = True
                h.log(
                    f"[DistPumpDoctor] Max attempts reached "
                    f"({self.MAX_PUMP_DOCTOR_ATTEMPTS}), sending critical glitch"
                )
                h._send_to(
                    h.ltn,
                    Glitch(
                        FromGNodeAlias=h.layout.scada_g_node_alias,
                        Node=h.node.Name,
                        Type=LogLevel.Critical,
                        Summary="Dist Pump Failed!!",
                        Details=(
                            f"Dist Pump doctor tried {self.attempts} times; "
                            "manual intervention required"
                        ),
                    ),
                )
                return

            h.log("[DistPumpDoctor] Starting...")
            h._send_to(
                h.ltn,
                Glitch(
                    FromGNodeAlias=h.layout.scada_g_node_alias,
                    Node=h.node.Name,
                    Type=LogLevel.Warning,
                    Summary="DistPumpDoctor starting",
                    Details=f"Attempt {self.attempts + 1}/{self.MAX_PUMP_DOCTOR_ATTEMPTS}",
                ),
            )

            if not h.layout.zone_list:
                h.log("[DistPumpDoctor] No zones found")
                return

            # Switch zones to SCADA
            for zone in h.layout.zone_list:
                h.heatcall_ctrl_to_scada(zone=zone, from_node=h_node)

            # Set DFR to zero
            h.services.send_threadsafe(
                Message(
                    Src=h.name,
                    Dst=h.primary_scada.name,
                    Payload=AnalogDispatch(
                        FromGNodeAlias=h.layout.ltn_g_node_alias,
                        FromHandle="auto",
                        ToHandle="auto.dist-010v",
                        AboutName="dist-010v",
                        Value=0,
                        TriggerId=str(uuid.uuid4()),
                        UnixTimeMs=int(time.time() * 1000),
                    ),
                )
            )

            await h.await_with_watchdog(5)

            for zone in h.layout.zone_list:
                h.stat_ops_close_relay(zone=zone, from_node=h_node)

            h.log("[DistPumpDoctor] Waiting for dist flow")
            flow_detected = await self.wait_for_dist_flow()

            if flow_detected:
                h.log("[DistPumpDoctor] Dist flow detected – success")
                self.attempts = 0
                h.zone_controller_triggered_at = None
            else:
                h.log(
                    f"[DistPumpDoctor] No dist flow after "
                    f"{self.MAX_WAIT_SECONDS}s"
                )
                self.attempts += 1

        except Exception as e:
            h.log(f"[DistPumpDoctor] Internal error: {e}")
            h._send_to(
                h.ltn,
                Glitch(
                    FromGNodeAlias=h.layout.scada_g_node_alias,
                    Node=h.node.Name,
                    Type=LogLevel.Warning,
                    Summary="DistPumpDoctor internal error",
                    Details=str(e),
                ),
            )

        finally:
            h.log("[DistPumpDoctor] Restoring defaults")
            h.set_010_defaults()
            for zone in h.layout.zone_list:
                h.heatcall_ctrl_to_stat(zone=zone, from_node=h_node)
            await h.await_with_watchdog(5)
            for zone in h.layout.zone_list:
                h.stat_ops_open_relay(zone=zone, from_node=h_node)

            self.running = False

    async def wait_for_dist_flow(
        self,
        poll_s: float = 2.0,
    ) -> bool:
        """
        Wait up to MAX_WAIT_SECONDS for distribution flow to exceed threshold.
        Returns True if flow is detected, False on timeout.
        """
        deadline = time.monotonic() + self.MAX_WAIT_SECONDS

        while time.monotonic() < deadline:
            flow = self.host.data.latest_channel_values.get(H0CN.dist_flow)
            if flow is not None and flow > self.THRESHOLD_FLOW_GPM_X100:
                return True

            await self.host.await_with_watchdog(poll_s)

        return False