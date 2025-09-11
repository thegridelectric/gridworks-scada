'''
Python version: 3.8.10
Modules:
Pyserial version: 3.4
Requires pyserial module:
    pip3 install pyserial
'''

import serial
import time

readings_times = []
readings_values = []

# Open connection to serial port
sp = serial.Serial(
    port='/dev/ttyACM0',
    baudrate=9600,
    parity=serial.PARITY_EVEN,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.SEVENBITS,
    xonxoff=0,
    timeout=5
)

# Meter Number (12-digit)
METER = b"000300015310"


# Send Request A to v4 Meter
sp.write(b"\x2F\x3F" + METER + b"\x30\x30\x21\x0D\x0A")

# Get meter response
response = sp.read(255)
# print("\nRaw hex response:")
# print(" ".join("{0:02x}".format(c) for c in response))

# Define all keys, their byte lengths, and whether to decode as ASCII
key_byte_lengths = [
    ("Packet Source", 1, False),
    ("Meter Model", 2, False),
    ("Firmware Version", 1, False),
    ("Meter Number", 12, True),
    ("Kilowatt Hour Total", 8, True),
    ("Reactive Energy Total", 8, True),
    ("Rev Kilowatt Hour Total", 8, True),
    ("Kilowatt Hour L1", 8, True),
    ("Kilowatt Hour L2", 8, True),
    ("Kilowatt Hour L3", 8, True),
    ("Reverse Kilowatt Hour L1", 8, True),
    ("Reverse Kilowatt Hour L2", 8, True),
    ("Reverse Kilowatt Hour L3", 8, True),
    ("Resettable Kilowatt Hour Total", 8, True),
    ("Resettable Reverse Kilowatt Hour Total", 8, True),
    ("RMS Volts L1", 4, True),
    ("RMS Volts L2", 4, True),
    ("RMS Volts L3", 4, True),
    ("Amps L1", 5, True),
    ("Amps L2", 5, True),
    ("Amps L3", 5, True),
    ("RMS Watts L1", 7, True),
    ("RMS Watts L2", 7, True),
    ("RMS Watts L3", 7, True),
    ("RMS Total Watts", 7, True),
    ("Cos Theta L1", 4, True),
    ("Cos Theta L2", 4, True),
    ("Cos Theta L3", 4, True),
    ("Reactive Power L1", 7, True),
    ("Reactive Power L2", 7, True),
    ("Reactive Power L3", 7, True),
    ("Reactive Power Total", 7, True),
    ("Line Frequency", 4, True),
    ("Pulse Count 1", 8, True),
    ("Pulse Count 2", 8, True),
    ("Pulse Count 3", 8, True),
    ("Pulse Input State", 1, True),
    ("Current Direction", 1, True),
    ("Outputs", 1, True),
    ("Kilowatt Hour Decimal Places", 1, True),
    ("Reserved", 2, True),
    ("Date and Time", 14, True)
]

selected_keys = [
    "RMS Watts L1",
    "Date and Time"
]

# Calculate total payload length
payload_length = sum(length for _, length, _ in key_byte_lengths)
payload = response[:payload_length]

# Parse and decode all values
values = []
offset = 0
for key, length, as_ascii in key_byte_lengths:
    segment = payload[offset:offset + length]
    if as_ascii:
        try:
            value = segment.decode('ascii').strip()
        except UnicodeDecodeError:
            value = "<decode error>"
    else:
        value = int.from_bytes(segment, byteorder='big')
    values.append(value)
    offset += length

result_dict = {key: value for (key, _, _), value in zip(key_byte_lengths, values)}

# Format date and time
date = f"20{result_dict['Date and Time'][:2]}-{result_dict['Date and Time'][2:4]}-{result_dict['Date and Time'][4:6]}"
timing = f"{result_dict['Date and Time'][8:10]}:{result_dict['Date and Time'][10:12]}:{result_dict['Date and Time'][12:14]}"
result_dict["Date and Time"] = f"{date} {timing} (UTC-{result_dict['Date and Time'][6:8]})"

for key, value in result_dict.items():
    if key in selected_keys:
        print(f"{key}: {value}")
        if key == "RMS Watts L1":
            readings_times.append(time.time())
            readings_values.append(int(value))

# time.sleep(0.1)

print(readings_times)
print(readings_values)

# Send "Close" command to meter
sp.write(b"\x01\x42\x30\x03\x75")

# Close serial port
sp.close()