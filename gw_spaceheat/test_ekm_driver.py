#!/usr/bin/env python3
"""
Test script for EKM Omnimeter Power Meter Driver
This script tests the basic functionality of the EKM driver without requiring
the full SCADA system infrastructure.
"""

import logging
import sys
import time
from typing import Optional

# Add the gw_spaceheat directory to the path so we can import our modules
sys.path.insert(0, '.')

from gw_spaceheat.drivers.power_meter.ekm_omnimeter_pulse_ul_v4 import EKM_Omnimeter_PowerMeterDriver
from gw_spaceheat.drivers.power_meter.ekm_omnimeter_pulse_ul_v4 import TryConnectResult

# Mock classes for testing
class MockElectricMeterComponent:
    class GT:
        MeterNumber = "000300015310"
    
    gt = GT()

class MockScadaSettings:
    class Logging:
        base_log_name = "test_ekm_driver"
    
    logging = Logging()

class MockDataChannel:
    def __init__(self, name: str, telemetry_name: str):
        self.Name = name
        self.TelemetryName = telemetry_name

def test_ekm_driver():
    """Test the EKM Omnimeter driver functionality"""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("test_ekm_driver")
    
    # Create mock objects
    component = MockElectricMeterComponent()
    settings = MockScadaSettings()
    
    # Create the driver
    driver = EKM_Omnimeter_PowerMeterDriver(component, settings, logger)
    
    print("Testing EKM Omnimeter Power Meter Driver")
    print("=" * 50)
    
    # Test 1: Try to connect
    print("\n1. Testing connection...")
    try:
        connect_result = driver.try_connect(first_time=True)
        if connect_result.is_ok():
            result = connect_result.value
            print(f"   Connection result: {result}")
            print(f"   Connected: {result.connected}")
            print(f"   Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"     Warning: {warning}")
        else:
            print(f"   Connection failed: {connect_result.value}")
    except Exception as e:
        print(f"   Connection error: {e}")
    
    # Test 2: Read hardware UID
    print("\n2. Testing hardware UID read...")
    try:
        uid_result = driver.read_hw_uid()
        if uid_result.is_ok():
            result = uid_result.value
            print(f"   UID result: {result}")
            print(f"   UID value: {result.value}")
            print(f"   Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"     Warning: {warning}")
        else:
            print(f"   UID read failed: {uid_result.value}")
    except Exception as e:
        print(f"   UID read error: {e}")
    
    # Test 3: Read power
    print("\n3. Testing power read...")
    try:
        power_channel = MockDataChannel("Power", "PowerW")
        power_result = driver.read_power_w(power_channel)
        if power_result.is_ok():
            result = power_result.value
            print(f"   Power result: {result}")
            print(f"   Power value: {result.value} W")
            print(f"   Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"     Warning: {warning}")
        else:
            print(f"   Power read failed: {power_result.value}")
    except Exception as e:
        print(f"   Power read error: {e}")
    
    # Test 4: Read current
    print("\n4. Testing current read...")
    try:
        current_channel = MockDataChannel("Current", "CurrentRmsMicroAmps")
        current_result = driver.read_current_rms_micro_amps(current_channel)
        if current_result.is_ok():
            result = current_result.value
            print(f"   Current result: {result}")
            print(f"   Current value: {result.value} μA")
            print(f"   Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"     Warning: {warning}")
        else:
            print(f"   Current read failed: {current_result.value}")
    except Exception as e:
        print(f"   Current read error: {e}")
    
    # Clean up
    print("\n5. Cleaning up...")
    driver.clean_client()
    print("   Driver cleaned up")
    
    print("\nTest completed!")

if __name__ == "__main__":
    test_ekm_driver() 