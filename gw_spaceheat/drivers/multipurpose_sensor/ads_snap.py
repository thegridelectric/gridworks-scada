import math

import adafruit_ads1x15.ads1115 as ADS
import board
import busio
from adafruit_ads1x15.analog_in import AnalogIn

PI_VOLTAGE = 5
# 298 Kelvin is 25 Celsius
THERMISTOR_T0_DEGREES_KELVIN = 298
# NTC THermistors are 10 kOhms at 25 deg C
THERMISTOR_R0_OHMS = 10000
# NTC Thermistors have a "rated beta" on their data sheet
THERMISTOR_BETA = 3977
# Then, there is our pull-up resistor
VOLTAGE_DIVIDER_R_OHMS = 8200


def thermistor_temp_f_beta_formula(voltage: float) -> float:
    rd: int = int(VOLTAGE_DIVIDER_R_OHMS)
    r0: int = int(THERMISTOR_R0_OHMS)
    beta: int = int(THERMISTOR_BETA)
    t0: int = int(THERMISTOR_T0_DEGREES_KELVIN)
    # Calculate the resistance of the thermistor
    rt = rd * voltage / (PI_VOLTAGE - voltage)
    # Calculate the temperature in degrees Celsius. Note that 273 is
    # 0 degrees Celsius as measured in Kelvin.
    temp_c = 1 / ((1 / t0) + (math.log(rt / r0) / beta)) - 273
    return temp_c


# Create the I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Create the ADC object using the I2C bus
ads = {}
ads[0] = ADS.ADS1115(address=int("0x48", 16), i2c=i2c)
ads[1] = ADS.ADS1115(address=int("0x49", 16), i2c=i2c)
ads[2] = ADS.ADS1115(address=int("0x4b", 16), i2c=i2c)

# Create single-ended input on channel 0

# Create differential input between channel 0 and 1
# chan = AnalogIn(ads, ADS.P0, ADS.P1)
for i in [0, 1, 2]:
    chan1 = AnalogIn(ads[i], ADS.P0)
    v1 = chan1.voltage
    temp1 = thermistor_temp_f_beta_formula(v1)
    num1 = i * 4 + 1
    print(f"Channel {num1}: voltage {round(v1,3)} V, temp {round(temp1,1)} C")

    chan2 = AnalogIn(ads[i], ADS.P1)
    v2 = chan2.voltage
    temp2 = thermistor_temp_f_beta_formula(v2)
    num2 = i * 4 + 2
    print(f"Channel {num2}: voltage {round(v2,3)} V, temp {round(temp2,1)} C")

    chan3 = AnalogIn(ads[i], ADS.P2)
    v3 = chan3.voltage
    temp3 = thermistor_temp_f_beta_formula(v3)
    num3 = i * 4 + 3
    print(f"Channel {num3}: voltage {round(v3,3)} V, temp {round(temp3,1)} C")

    chan4 = AnalogIn(ads[i], ADS.P3)
    v4 = chan4.voltage
    temp4 = thermistor_temp_f_beta_formula(v4)
    num4 = i * 4 + 4
    print(f"Channel {num4}: voltage {round(v4,3)} V, temp {round(temp4,1)} C")
