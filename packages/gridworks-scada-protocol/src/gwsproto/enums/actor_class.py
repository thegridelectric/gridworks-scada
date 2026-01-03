from enum import auto

from gw.enums import GwStrEnum


class ActorClass(GwStrEnum):
    """
    Determines the code running Spaceheat Nodes supervised by Spaceheat SCADA software
    Values:
      - NoActor: A SpaceheatNode that does not have any code running on its behalf within
        the SCADA, but is instead only a reference object (for example, a tank of hot water
        or a resistive element) that can be discussed (for example, the power drawn by the resistive
        element can be measured) or evaluated (for example, a set of 5 different temperatures
        in different places on the tank can be used to estimate total thermal energy in the
        tank).
      - Scada: The SCADA actor is the prime piece of code running and supervising other
        ProActors within the SCADA code. It is also responsible for managing the state of TalkingWith
        the AtomicTNode, as well maintaining and reporting a boolean state variable that indicates
        whether it is following dispatch commands from the AtomicTNode XOR following dispatch
        commands from its own HomeAlone actor.
      - HomeAlone: HomeAlone is an abstract Spaceheat Actor responsible for dispatching
        the SCADA when it is not talking with the AtomicTNode.
      - BooleanActuator: A SpaceheatNode representing a generic boolean actuator capable
        of turning on (closing a circuit) or turning off (opening a circuit). If the device
        is a relay that can be directly energized or de-energized, recommend using Relay actor
        instead.
      - PowerMeter: A SpaceheatNode representing the power meter that is used to settle
        financial transactions with the TerminalAsset. That is, this is the power meter whose
        accuracy is certified in the creation of the TerminalAsset GNode via creation of the
        TaDeed. [More Info](https://gridworks.readthedocs.io/en/latest/terminal-asset.html).
      - Atn: A SpaceheatNode representing the AtomicTNode. Note that the code running
        the AtomicTNode is not local within the SCADA code, except for a stub used for testing
        purposes. [More Info](https://gridworks.readthedocs.io/en/latest/atomic-t-node.html).
      - SimpleSensor: A SpaceheatNode representing a sensor that measures a single category
        of quantity (for example, temperature) for a single object (for example, on a pipe). [More Info](https://gridworks-protocol.readthedocs.io/en/latest/simple-sensor.html).
      - MultipurposeSensor: A sensor that either reads multiple kinds of readings from
        the same sensing device (for example reads current and voltage), reads multiple different
        objects (temperature from two different thermisters) or both. [More Info](https://gridworks-protocol.readthedocs.io/en/latest/multipurpose-sensor.html).
      - Thermostat: A SpaceheatNode representing a thermostat.
      - HubitatTelemetryReader: A generic actor for reading telemetry data from a Hubitat
        Home Automation Hub LAN API. [More Info](https://drive.google.com/drive/u/0/folders/1AqAU_lC2phzuI9XRYvogiIYA7GXNtlr6).
      - HubitatTankModule: The actor for running a GridWorks TankModule, comprised of
        two Z-Wave Fibaro temp sensors built together inside a small container that has 4 thermistors
        attached. These are designed to be installed from top (1) to bottom (4) on a stratified
        thermal storage tank. [More Info](https://drive.google.com/drive/u/0/folders/1GSxDd8Naf1GKK_fSOgQU933M1UcJ4r8q).
      - HubitatPoller: An actor for representing a somewhat generic ShNode (like a thermostat)
        that can be polled through the Hubitat.
      - I2cRelayMultiplexer: Responsible for maintaining a single i2c bus object
      - FlowTotalizer: Attached to a driver that reads liquid flow by counting pulses
        from a flow meter that creates pulses and integrating the result (known as a totalizer
        in the industry).
      - Relay: An actor representing a relay. If the device is indeed relay that can be
        directly energized or de-energized, recommend using Relay instead of BooleanActuator
      - Admin: Actor for taking control of all of the actuators - flattening the hierarchy
        and disabling all finite state machines.
      - Fsm: Actor Class for Finite State Machine actors. For these actors, the code is
        determined by the ShNode Name instead of just the ActorClass.
      - Parentless: An actor that has no parent and is also not the primary SCADA. Used
        when there are multiple devices in the SCADA's system. For example, two Pis - one running
        the primary SCADA code and temp sensors, the other running relays and 0-10V output devices.
        A Parentless actor on the second Pi is responsible for spinning up the relay- and 0-10V
        output actors.
      - Hubitat: An actor for representing a Hubitat for receiving Hubitat events over
        HTTP.
      - HoneywellThermostat: An actor for representing a Honeywell Hubitat thermostat
        which can load thermostat heating state change messages into status reports.
      - ApiTankModule
      - ApiFlowModule
      - PicoCycler
      - I2cDfrMultiplexer
      - ZeroTenOutputer
      - AtomicAlly: Direct report of Atn when the Scada is in Atn mode.
      - SynthGenerator
      - FakeAtn
      - PumpDoctor: An actor that monitors and resets pumps if necessary
      - DefrostManager: Actor that handles the defrost cycle of a heat pump.

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
        return "008"
