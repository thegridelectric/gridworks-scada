from typing import TYPE_CHECKING
import uuid
import time
from gwsproto.enums import LogLevel
from gwsproto.data_classes.house_0_names import H0CN
from gwsproto.named_types import AnalogDispatch, Glitch


if TYPE_CHECKING:
    from actors.procedural.procedural_host import ProceduralHost
class StorePumpDoctor:
    """
    Procedural, non-transactive recovery for storage pump failures.
    See actors.procedural for architectural constraints.
    """
    MAX_PUMP_DOCTOR_ATTEMPTS = 3
    MAX_WAIT_SECONDS = 15
    THRESHOLD_FLOW_GPM_X100 = 50

    def __init__(self, host: "ProceduralHost"):
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

        if self.running:
            h.log("[StorePumpDoctor] Already running, skipping")
            return

        self.running = True
        try:
            if self.attempts >= self.MAX_PUMP_DOCTOR_ATTEMPTS:
                if self.exhausted:
                    return

                self.exhausted = True
                h.log(
                    f"[StorePumpDoctor] Max attempts reached "
                    f"({self.MAX_PUMP_DOCTOR_ATTEMPTS}), sending critical glitch"
                )
                h._send_to(
                    h.ltn,
                    Glitch(
                        FromGNodeAlias=h.layout.scada_g_node_alias,
                        Node=h.node.Name,
                        Type=LogLevel.Critical,
                        Summary="Store Pump Failed!!",
                        Details=(
                            f"Store Pump doctor tried {self.attempts} times; "
                            "manual intervention required"
                        ),
                    ),
                )
                return

            h.log("[StorePumpDoctor] Starting...")
            h._send_to(
                h.ltn,
                Glitch(
                    FromGNodeAlias=h.layout.scada_g_node_alias,
                    Node=h.node.Name,
                    Type=LogLevel.Warning,
                    Summary="StorePumpDoctor starting",
                    Details=f"Attempt {self.attempts + 1}/{self.MAX_PUMP_DOCTOR_ATTEMPTS}",
                ),
            )

            h.turn_off_store_pump()

            # Set 0-10 to zero
            h._send_to(
                h.primary_scada,
                AnalogDispatch(
                        FromGNodeAlias=h.layout.ltn_g_node_alias,
                        FromHandle=h.command_node.handle,
                        ToHandle=h.store_010v.handle,
                        AboutName=h.store_010v.name,
                        Value=0,
                        TriggerId=str(uuid.uuid4()),
                        UnixTimeMs=int(time.time() * 1000),
                ),
            )

            await h.await_with_watchdog(5)

            h.turn_on_store_pump()

            h.log("[StorePumpDoctor] Waiting for store flow")
            flow_detected = await self.wait_for_store_flow()

            if flow_detected:
                h.log("[StorePumpDoctor] Store flow detected - success")
                self.attempts = 0
            else:
                h.log(
                    f"[StorePumpDoctor] No store flow after "
                    f"{self.MAX_WAIT_SECONDS}s"
                )
                self.attempts += 1

        except Exception as e:
            h.log(f"[StorePumpDoctor] Internal error: {e}")
            h._send_to(
                h.ltn,
                Glitch(
                    FromGNodeAlias=h.layout.scada_g_node_alias,
                    Node=h.node.Name,
                    Type=LogLevel.Warning,
                    Summary="StorePumpDoctor internal error",
                    Details=str(e),
                ),
            )

        finally:
            h.log("[StorePumpDoctor] Restoring defaults")
            h.set_010_defaults()

            self.running = False

    async def wait_for_store_flow(
        self,
        poll_s: float = 2.0,
    ) -> bool:
        """
        Wait up to MAX_WAIT_SECONDS for storage flow to exceed threshold.
        Returns True if flow is detected, False on timeout.
        """
        deadline = time.monotonic() + self.MAX_WAIT_SECONDS

        while time.monotonic() < deadline:
            flow = self.host.data.latest_channel_values.get(H0CN.store_flow)
            if flow is not None and flow > self.THRESHOLD_FLOW_GPM_X100:
                return True

            await self.host.await_with_watchdog(poll_s)

        return False