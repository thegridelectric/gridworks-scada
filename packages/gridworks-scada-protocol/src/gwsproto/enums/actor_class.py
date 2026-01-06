from enum import auto

from gw.enums import GwStrEnum


class ActorClass(GwStrEnum):
    """
    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#shactorclass)
      - [More Info](https://gridworks-protocol.readthedocs.io/en/latest/actor-class.html)
    """

    NoActor = auto()
    Scada = auto()
    HomeAlone = auto()
    BooleanActuator = auto()
    PowerMeter = auto()
    Atn = auto()
    SimpleSensor = auto()
    MultipurposeSensor = auto()
    Thermostat = auto()
    HubitatTelemetryReader = auto()
    HubitatTankModule = auto()
    HubitatPoller = auto()
    I2cRelayMultiplexer = auto()
    FlowTotalizer = auto()
    Relay = auto()
    Admin = auto()
    Fsm = auto()
    Parentless = auto()
    Hubitat = auto()
    HoneywellThermostat = auto() # TODO: change to ExternalThermostat
    ApiTankModule = auto()
    ApiFlowModule = auto()
    PicoCycler = auto()
    I2cDfrMultiplexer = auto()
    ZeroTenOutputer = auto()
    AtomicAlly = auto()
    SynthGenerator = auto()
    FakeAtn = auto()
    PumpDoctor = auto()
    StratBoss = auto()
    HpRelayBoss = auto()
    SiegLoop = auto()
    HpBoss = auto()
    ApiBtuMeter = auto()
    DerivedGenerator = auto()

    @classmethod
    def default(cls) -> "ActorClass":
        return cls.NoActor

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "sh.actor.class"

    @classmethod
    def enum_version(cls) -> str:
        return "009"
