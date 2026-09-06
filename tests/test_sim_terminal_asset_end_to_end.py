# The biggest test: one simulated terminal asset driven end to end, from the
# fake i2c chips through the real actors to local-control behavior over time.
# All comment for now. This is the target the simulated-test-environment work
# builds toward, and the place to note what functional requirements it can
# carry for us as the rungs land. Simplest first; each rung adds surface area.
#
# The path under test (the same code a real house runs):
#
#   layout (SimGw108 board record, sim device types)
#     -> I2cBus over SimI2c: SimTca9555 expanders, SimMcp4728 DAC, SimAds1115
#     -> I2cThermistorReader (ADS1115 dance, classification) -> channel values
#     -> DerivedGenerator, HpBoss, LocalControl -> relay FSMs, ZeroTenOutputer
#     -> SimTca9555 output bits / SimMcp4728 registers, which the PLANT reads
#     -> plant physics (room, store, pump, heat pump) -> new temperatures
#     -> inverse transform -> ADS1115 codes in SimAds1115, and around again
#
# Rungs, in order:
#
# 1. The simplest simulated terminal asset and its layout (build-plant.md's
#    `gw1.simple.sim.layout`): one board, one thermistor ADC with a few
#    channels, one relay, one 0-10V output, one room, one store. Nothing
#    the four fall layouts would contradict (no assumed buffer, iso valve,
#    or water tanks in the shared shape).
# 2. Sensors from physics, not standing values. Today SimSensorActor emits
#    constants (50 C water, 70 F air) and SimAds1115 returns one voltage.
#    The plant holds a temperature per thermistor; the sim chip applies the
#    inverse of the reader's transform (temperature -> beta -> resistance
#    -> divider voltage -> ADS1115 raw code, per mux channel) so the reader's
#    real classification and conversion are what the test exercises.
# 3. Actuators feed back. The plant reads relay state from the expanders'
#    output flip-flops and pump speed from the DAC's channel register, so a
#    closed heat-pump relay warms the store and a DAC level moves the flow.
# 4. Sim time. The time coordinator's timesteps pace both the plant and the
#    actors' timers (the sim-time bridge is interim; the harness owns pacing).
# 5. Behavior over time: a scripted heat call -> LocalControl asks for heat
#    -> HP relay closes -> store warms -> call ends -> relay opens, with the
#    derived channels and state reports coherent throughout.
#
# Functional requirements this test can carry once the rungs exist:
#
# - Thermistor classification: shorted, broken/missing, live; the config
#   readback gate under a mid-sequence chip reset.
# - Expander reset repair: SimTca9555.power_on_reset mid-run, the bus
#   detects and re-initializes, every i2c relay re-asserts its target.
# - DAC output: boot EEPROM verify passes when the sim EEPROM is seeded from
#   the layout's PowerOn values, reprograms when it is not; dispatch writes
#   the register; the 60 s heartbeat re-asserts the LAST COMMANDED value.
# - Relay FSMs report state on every actuation, simulated or not.
# - Admin: capabilities projection and AdminAnalogDispatch/relay dispatch
#   land under the admin tree, and the tree reverts when admin releases.
# - LocalControl and HpBoss state machines over a scripted day (peak and
#   off-peak, a cold zone, a dormant HP), with no dead actor coroutines.
# - LTN <-> SCADA contract flow with temperatures that come from the plant,
#   not a constant.
# - Watchdog: a dead actor stops the keepalive and the process exits for
#   systemd, on the sim clock.
# - Comm loss: the broker blackhole shape, with the persister's un-acked
#   event replay on reconnect.
#
# The DAC output experiment we are running RIGHT NOW, seen through this test
# (experiments/2026-09-05-dac-output-bench/): the bench asks "does a dispatched
# level reach the chip and does the heartbeat hold it". With rungs 1 and 3 in
# place it would run locally like this: boot the simple sim layout; assert
# the outputer's boot verify reads the seeded EEPROM back clean; send an
# AdminAnalogDispatch for the secondary-010v node at 5.5 V; assert
# SimMcp4728.register[channel] holds the code 2200 with the layout's vref and
# gain, and the channel reports 55; step sim time past one heartbeat and
# assert the register still holds 2200, not the power-on value; then, with
# the plant reading the DAC, assert the secondary flow channel rises. What
# the bench keeps for itself is the electrics: mux select, bus timing, the
# chip's EEPROM write cycle, and the pump actually turning. Both of this
# week's bench findings (a dispatch that silently reached the fake chip; a
# verify that reprogrammed a matching EEPROM) would have been a red local
# test before the pi was ever touched.
