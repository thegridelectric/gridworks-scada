import time
import math
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


PI_VOLTAGE = 5.1
# 298 Kelvin is 25 Celsius
THERMISTOR_T0_DEGREES_KELVIN = 298
# NTC THermistors are 10 kOhms at 25 deg C
THERMISTOR_R0_OHMS = 10000
# NTC Thermistors have a "rated beta" on their data sheet
THERMISTOR_BETA = 3977
# Then, there is our pull-up resistor
VOLTAGE_DIVIDER_R_OHMS = 10000


def thermistor_temp_c_beta_formula(
        voltage: float) -> float:
    rd: int = int(VOLTAGE_DIVIDER_R_OHMS)
    r0: int = int(THERMISTOR_R0_OHMS)
    beta: int = int(THERMISTOR_BETA)
    t0: int = int(THERMISTOR_T0_DEGREES_KELVIN)
    if voltage >= PI_VOLTAGE:
        return -500
    # Calculate the resistance of the thermistor
    rt = rd * voltage / (PI_VOLTAGE - voltage)
    # Calculate the temperature in degrees Celsius. Note that 273 is
    # 0 degrees Celsius as measured in Kelvin.
    temp_c = 1 / ((1 / t0) + (math.log(rt / r0) / beta)) - 273
    # Convert the temperature to degrees Fahrenheit
    temp_f = (temp_c * 9 / 5) + 32
    return temp_c


# Create the I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Create the ADC object using the I2C bus
ads = {}
ads[0] = ADS.ADS1115(address=int("0x48", 16), i2c=i2c)
ads[1] = ADS.ADS1115(address=int("0x49", 16), i2c=i2c)
ads[2] = ADS.ADS1115(address=int("0x4b", 16), i2c=i2c)

ads[0].gain = 0.6666666666666666
ads[1].gain = 0.6666666666666666
ads[2].gain = 0.6666666666666666
# ads[0].gain = 0.6666666666666666 gives a range up to +/- 6.144V
# Create single-ended input on channel 0

# Create differential input between channel 0 and 1
# chan = AnalogIn(ads, ADS.P0, ADS.P1)

while True:
    chanhot = AnalogIn(ads[0], ADS.P2)
    v_hot = chanhot.voltage
    temphot_c = thermistor_temp_c_beta_formula(v_hot)
    temphot_f = (temphot_c * 9 / 5) + 32

    chancold = AnalogIn(ads[1], ADS.P2)
    v_cold = chancold.voltage
    tempcold_c = thermistor_temp_c_beta_formula(v_cold)
    tempcold_f = (tempcold_c * 9 / 5) + 32

    chanmix = AnalogIn(ads[0], ADS.P0)
    v_mix = chanmix.voltage
    tempmix_c = thermistor_temp_c_beta_formula(v_mix)
    tempmix_f = (tempmix_c * 9 / 5) + 32

    print(
        f"Hot (a.hotstore.out.temp): {round(temphot_f,1)} F, Cold(a.buffer.out.temp): {round(tempcold_f,1)} F, MIX (a.distsourcewater.temp): {round(tempmix_f,1)} F")
    time.sleep(5)
