from enum import auto

from gw.enums import GwStrEnum


class MakeModel(GwStrEnum):
    """
    Determines Make/Model of device associated to a Spaceheat Node supervised by SCADA
    Values:
      - UnknownMake__UnknownModel
      - Egauge__4030: A power meter in Egauge's 403x line. [More Info](https://drive.google.com/drive/u/0/folders/1abJ-o9tlTscsQpMvT6SHxIm5j5aODgfA).
      - NCD__PR8-14-SPST: NCD's 4-channel high-power relay controller + 4 GPIO with I2C
        interface. [More Info](https://store.ncd.io/product/4-channel-high-power-relay-controller-4-gpio-with-i2c-interface/?attribute_pa_choose-a-relay=20-amp-spdt).
      - Adafruit__642: Adafruit's high-temp, water-proof 1-wire temp sensor. [More Info](https://www.adafruit.com/product/642).
      - GridWorks__TSnap1: Actual GridWorks TSnap 1.0 SCADA Box.
      - GridWorks__WaterTempHighPrecision: PlaceHolder for some new GridWorks designed
        device.
      - Gridworks__SimPm1: Simulated power meter.
      - SchneiderElectric__Iem3455: Schneider Electric IEM 344 utility meter.
      - GridWorks__SimBool30AmpRelay: Simulated relay.
      - OpenEnergy__EmonPi: Open Energy's open source multipurpose sensing device (including
        internal power meter). [More Info](https://docs.openenergymonitor.org/emonpi/technical.html).
      - GridWorks__SimTSnap1: Simulated SCADA Box.
      - Atlas__EzFlo: Atlas Scientific EZO Embedded Flow Meter Totalizer, pulse to I2C. [More Info](https://drive.google.com/drive/u/0/folders/142bBV1pQIbMpyIR_0iRUr5gnzWgknOJp).
      - Hubitat__C7__LAN1: This refers to a Hubitat C7 that has been configured in a specific
        way with respect to the APIs it presents on the Local Area Network. The Hubitat C7 is
        a home automation hub that supports building ZigBee and ZWave meshes, plugs into Ethernet,
        has a reasonable user interface and has an active community of open-source developers
        who create drivers and package managers for devices, and supports the creation of various
        types of APIs on the Local Area Network. [More Info](https://drive.google.com/drive/folders/1AqAU_lC2phzuI9XRYvogiIYA7GXNtlr6).
      - GridWorks__Tank_Module_1: This refers to a small module designed and assembled
        by GridWorks that is meant to be mounted to the side of a hot water tank. It requires
        24V DC and has 4 temperature sensors coming out of it labeled 1, 2, 3 and 4. It is meant
        to provide temperature readings (taken within a half a second of each other) of all
        4 of its sensors once a minute. [More Info](https://drive.google.com/drive/folders/1GSxDd8Naf1GKK_fSOgQU933M1UcJ4r8q).
      - Fibaro__Analog_Temp_Sensor: This enum refers to a Fibaro FGBS-222 home automation
        device that has been configured in a specific way. This includes (1) being attached
        to two 10K NTC thermistors and a specific voltage divider circuit that specifies its
        temperature as a function of voltage and (2) one of its potential free outputs being
        in-line with the power of a partner Fibaro, so that it can power cycle its partner (because
        there are reports of Fibaros no longer reporting temp change after weeks or months until
        power cylced). The Fibaro itself is a tiny (29 X 18 X 13 mm) Z-Wave device powered on
        9-30V DC that can read up to 6 1-wire DS18B20 temp sensors, 2 0-10V analog inputs and
        also has 2 potential free outputs. [More Info](https://drive.google.com/drive/u/0/folders/1Muhsvw00goppHIfGSEmreX4hM6V78b-m).
      - Amphenol__NTC_10K_Thermistor_MA100GG103BN: A small gauge, low-cost, rapid response
        NTC 10K Thermistor designed for medical applications. [More Info](https://drive.google.com/drive/u/0/folders/11HW4ov66UvxKAwqApW6IrtoXatZBLQkd).
      - YHDC__SCT013-100: YHDC current transformer. [More Info](https://en.yhdc.com/product/SCT013-401.html).
      - Magnelab__SCT-0300-050: Magnelab 50A current transformer.
      - GridWorks__MultiTemp1: GridWorks ADS 1115-based analog temperature sensor that
        has 12 channels (labeled 1-12) to read 12 10K NTC Thermistors. It is comprised of 3
        NCD ADS 1115 I2C temperature sensors with I2C Addresses 0x4b, 0x48, 0x49. [More Info](https://drive.google.com/drive/u/0/folders/1OuY0tunaad2Ie4Id3zFB7FcbEwHizWuL).
      - Krida__Emr16-I2c-V3: 16-Channel I2C Low Voltage Electromagnetic Relay Board. [More Info](https://drive.google.com/drive/u/0/folders/1jL82MTRKEh9DDmxJFQ2yU2cjqnVD9Ik7).
      - Omega__FTB8007HW-PT: A double-jet reed pulse producing Flow Meter with 3/4" pipe,
        one pulse per 1/10th of a gallon. [More Info](https://drive.google.com/drive/u/0/folders/1gPR4nIGUuEVyBqBjb2wfY1Znqh6MvKWw).
      - Istec_4440: A double-jet reed pulse producing Flow Meter with 3/4" pipe, somewhat
        strange pulse output. [More Info](https://drive.google.com/drive/u/0/folders/1nioNO_XeEzE4NQJKXvuFq74_HH1vwRc6).
      - Omega__FTB8010HW-PT: A double-jet reed pulse producingFlow Meter with 1" pipe,
        one pulse per gallon. Rated for water to 195F. [More Info](https://drive.google.com/drive/u/0/folders/1fiFr9hwYGeXZ1SmpxaSz_XROhfThGbq8).
      - Belimo__BallValve232VS: Belimo Ball Valve. Configurable to be either normally
        open or normally closed. Goes into its powered position over about a minute and winds
        up a spring as it does that. Moves back to un-powered position in about 20 seconds, [More Info](https://drive.google.com/drive/u/0/folders/1eTqPNKaKzjKSWwnvY36tZkkv4WVdvrR3).
      - Belimo__DiverterB332L: Belimo 3-way diverter valve, 1.25", 24 VAC, spring return
        actuator. [More Info](https://drive.google.com/drive/u/0/folders/1YF_JdUoXrT3bDoXvEwqEvAi7EjahErHk).
      - Taco__0034ePLUS: Taco 0034ePLUS 010V controllable pump. [More Info](https://drive.google.com/drive/u/0/folders/1GUaQnrfiJeAmmfMiZT1fjPPIXxcTtTsj).
      - Taco__007e: Taco 007e basic circulator pump. [More Info](https://drive.google.com/drive/u/0/folders/12LIMxHMFXujV7mY53IItKP3J2EaM2JlV).
      - Armstrong__CompassH: Armstrong CompassH 010V controllable pump. [More Info](https://drive.google.com/drive/u/0/folders/1lpdvjVYD9qk7AHQnRSoY9Xf_o_L0tY38).
      - Honeywell__T6-ZWave-Thermostat: Honeywell TH6320ZW2003 T6 Pro Series Z-Wave Thermostat. [More Info](https://drive.google.com/drive/u/0/folders/1mqnU95tOdeeSGA6o3Ac_sJ1juDy84BIE).
      - PRMFiltration__WM075: A double-jet reed pulse producing Flow Meter with 3/4" pipe,
        one pulse per gallon. Cheaper than omegas. [More Info](https://drive.google.com/drive/u/0/folders/1LW-8GHekH9I8vUtT7_xC_9KvkwfZBvid).
      - BellGossett__Ecocirc20_18: A 0-10V controllable pump that switches out of 0-10V
        control when sent a 0 V signal.
      - Tewa__TT0P-10KC3-T105-1500: A 10K NTC thermistor used for wrapping around water
        pipes. [More Info](https://drive.google.com/drive/u/0/folders/1lZFZbpjBFgAQ_wlnKJxmEeiN-EOV9Erl).
      - EKM__HOT-SPWM-075-HD: 3/4" horizontal hot water flow pulse meter, 1 pulse per
        1/100 cubic ft (~0.0748 gallons).
      - GridWorks__SimMultiTemp: Simulated 12-channel Ads111x-based analog temp sensor
      - GridWorks__SimTotalizer: Simulated I2c-based pulse counter.
      - Krida__Double-Emr16-I2c-V3: Two 16-Channel I2C Low Voltage Electromagnetic Relay
        Board, with first at address 0x20 and second at address 0x21
      - GridWorks__SimDouble16PinI2cRelay: Simulated I2c Relay board with two boards and
        32 pins (for dev code using Krida__Doubler-Emr16-I2c-V3).
      - GridWorks__TankModule2
      - GridWorks__PicoFlowHall
      - GridWorks__PicoFlowReed
      - Saier__Sen-HZG1WA
      - DFRobot__DFR0971_Times2: Two DfRobot DFR0971 i2c 0-10V analog output actuators,
        set so the first has address 0x5e and the second has address 0x5f

    For more information:
      - [ASLs](https://gridworks-type-registry.readthedocs.io/en/latest/)
      - [Global Authority](https://gridworks-type-registry.readthedocs.io/en/latest/enums.html#spaceheatmakemodel)
      - [More Info](https://gridworks-protocol.readthedocs.io/en/latest/make-model.html)
    """

    UNKNOWNMAKE__UNKNOWNMODEL = auto()
    EGAUGE__4030 = auto()
    NCD__PR814SPST = auto()
    ADAFRUIT__642 = auto()
    GRIDWORKS__TSNAP1 = auto()
    GRIDWORKS__WATERTEMPHIGHPRECISION = auto()
    GRIDWORKS__SIMPM1 = auto()
    SCHNEIDERELECTRIC__IEM3455 = auto()
    GRIDWORKS__SIMBOOL30AMPRELAY = auto()
    OPENENERGY__EMONPI = auto()
    GRIDWORKS__SIMTSNAP1 = auto()
    ATLAS__EZFLO = auto()
    HUBITAT__C7__LAN1 = auto()
    GRIDWORKS__TANK_MODULE_1 = auto()
    FIBARO__ANALOG_TEMP_SENSOR = auto()
    AMPHENOL__NTC_10K_THERMISTOR_MA100GG103BN = auto()
    YHDC__SCT013100 = auto()
    MAGNELAB__SCT0300050 = auto()
    GRIDWORKS__MULTITEMP1 = auto()
    KRIDA__EMR16I2CV3 = auto()
    OMEGA__FTB8007HWPT = auto()
    ISTEC_4440 = auto()
    OMEGA__FTB8010HWPT = auto()
    BELIMO__BALLVALVE232VS = auto()
    BELIMO__DIVERTERB332L = auto()
    TACO__0034EPLUS = auto()
    TACO__007E = auto()
    ARMSTRONG__COMPASSH = auto()
    HONEYWELL__T6ZWAVETHERMOSTAT = auto()
    PRMFILTRATION__WM075 = auto()
    BELLGOSSETT__ECOCIRC20_18 = auto()
    TEWA__TT0P10KC3T1051500 = auto()
    EKM__HOTSPWM075HD = auto()
    GRIDWORKS__SIMMULTITEMP = auto()
    GRIDWORKS__SIMTOTALIZER = auto()
    KRIDA__DOUBLEEMR16I2CV3 = auto()
    GRIDWORKS__SIMDOUBLE16PINI2CRELAY = auto()
    GRIDWORKS__TANKMODULE2 = auto()
    GRIDWORKS__PICOFLOWHALL = auto()
    GRIDWORKS__PICOFLOWREED = auto()
    SAIER__SENHZG1WA = auto()
    DFROBOT__DFR0971_TIMES2 = auto()
    GRIDWORKS__TANKMODULE3 = auto()
    GRIDWORKS__GW101 = auto()

    @classmethod
    def default(cls) -> "MakeModel":
        return cls.UNKNOWNMAKE__UNKNOWNMODEL

    @classmethod
    def values(cls) -> list[str]:
        return [elt.value for elt in cls]

    @classmethod
    def enum_name(cls) -> str:
        return "spaceheat.make.model"

    @classmethod
    def enum_version(cls) -> str:
        return "006"
