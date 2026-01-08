from enum import auto

from gw.enums import GwStrEnum


class RelayWiringConfig(GwStrEnum):
    """
    While some relays come with only two terminals and a default configuration, many come with
    a common terminal (COM), normally open terminal (NO) and normally closed terminal (NC).
    When the relay is de-energized, the circuit between COM and Normally Closed is closed. When
    the relay is energized, the circuit between COM and Normally Open is closed. This enum is
    about how one wires such a relay into a circuit.
    Values:
      - NormallyClosed: When the relay is de-energized, the circuit is closed (circuit
        is wired through COM and NC).
      - NormallyOpen: When the relay is de-energized, the circuit is open (circuit is
        wired through COM and NC).
      - DoubleThrow: COM, NC, and NO are all connected to parts of the circuit. For example,
        NC could activate a heat pump and NO could activate a backup oil boiler. The Double
        Throw configuration allows for switching between these two.

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#relaywiringconfig)
      - [More Info](https://gridworks-protocol.readthedocs.io/en/latest/relays.html)
    """

    NormallyClosed = auto()
    NormallyOpen = auto()
    DoubleThrow = auto()

    @classmethod
    def default(cls) -> "RelayWiringConfig":
        return cls.NormallyClosed

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "relay.wiring.config"

    @classmethod
    def enum_version(cls) -> str:
        return "000"
