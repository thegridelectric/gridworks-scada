import asyncio
import time
from typing import Dict, Optional, Sequence, cast

from gwproto.message import Message
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from result import Ok, Err, Result

from actors.sh_node_actor import ShNodeActor
from scada_app_interface import ScadaAppInterface

from gwsproto.enums import (
    MakeModel,
    ChangeRelayPin,
    FsmReportType,
    RelayEnergizationState,
    LogLevel,
)

from gwsproto.named_types import (
    FsmAtomicReport,
    Glitch,
)

from gwsproto.named_types.i2c_write_bit import I2cWriteBit
from gwsproto.data_classes.components.i2c_multichannel_dt_relay_component import (
    I2cMultichannelDtRelayComponent,
)
from gwsproto.data_classes.sh_node import ShNode


class I2cRelayBoardActor(ShNodeActor):
    """Board-level authority for translating relay semantics into I2C bus command"""

    BOARD_LOOP_S = 60

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)

        # ---- Component ownership & validation ----
        component = getattr(self.node, "component", None)
        if component is None:
            raise ValueError(f"{self.name} has no component")

        if not isinstance(component, I2cMultichannelDtRelayComponent):
            raise ValueError(
                f"{self.name} expects I2cMultichannelDtRelayComponent, "
                f"got {type(component)}"
            )

        self.component = component
        self.cac = component.cac
        self.gt = component.gt

        # ---- Bus routing ----
        self.i2c_bus_name = self.gt.I2cBus

        # ---- Internal state ----
        self._stop_requested = False

        # RelayIdx -> current energization state
        self.relay_state: Dict[int, RelayEnergizationState] = {}

        # ---- MakeModel dispatch ----
        if self.cac.MakeModel == MakeModel.GRIDWORKS__SCADA_GW108:
            self._initialize_gw108()
        else:
            raise ValueError(
                f"I2cRelayBoardActor does not support MakeModel {self.cac.MakeModel}"
            )

    def _initialize_gw108(self) -> None:
        """
        Initialize GW108-specific relay board semantics.
        """
        # Validate relay config list
        for cfg in self.gt.ConfigList:
            self.relay_state[cfg.RelayIdx] = RelayEnergizationState.DeEnergized

        self.log(
            f"[GW108] Initialized I2C relay board with "
            f"{len(self.relay_state)} relays on bus {self.i2c_bus_name}"
        )
