"""Type power.watts, version 000"""

from typing import Literal

from pydantic import BaseModel


class PowerWatts(BaseModel):
    """
    Real-time power of TerminalAsset in Watts.

    Used by a SCADA -> Atn or Atn -> AggregatedTNode to report real-time power of their TerminalAsset.
    Positive number means WITHDRAWAL from the grid - so generating electricity creates a negative
    number. This message is considered worse than useless to send after the first attempt, and
    does not require an ack. Shares the same purpose as gs.pwr, but is not designed to minimize
    bytes so comes in JSON format.
    """

    Watts: int
    TypeName: Literal["power.watts"] = "power.watts"
    Version: str = "000"
