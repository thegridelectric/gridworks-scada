"""An integration test which verifies some of the messages expected to be exchanged after system startup"""

import load_house
from actors.boolean_actuator import BooleanActuator
from actors.power_meter import PowerMeter
from actors.simple_sensor import SimpleSensor
from data_classes.sh_node import ShNode
from schema.gt.gt_dispatch_boolean.gt_dispatch_boolean_maker import GtDispatchBoolean_Maker
from test.utils import ScadaRecorder, AtnRecorder, EarRecorder, wait_for


def test_message_exchange(tmp_path, monkeypatch):
    """Run various nodes and verify they send each other messages as expected"""
    monkeypatch.chdir(tmp_path)
    debug_logs_path = tmp_path / "output/debug_logs"
    debug_logs_path.mkdir(parents=True, exist_ok=True)
    load_house.load_all()
    scada = ScadaRecorder(node=ShNode.by_alias["a.s"], logging_on=True)
    atn = AtnRecorder(node=ShNode.by_alias["a"], logging_on=True)
    ear = EarRecorder(logging_on=True)
    elt_relay = BooleanActuator(ShNode.by_alias["a.elt1.relay"], logging_on=True)
    meter = PowerMeter(node=ShNode.by_alias["a.m"], logging_on=True)
    thermo = SimpleSensor(node=ShNode.by_alias["a.tank.temp0"], logging_on=True)
    actors = [scada, atn, ear, elt_relay, meter, thermo]

    try:
        for actor in actors:
            actor.start()
        for actor in actors:
            if hasattr(actor, "client"):
                wait_for(
                    actor.client.is_connected,
                    1,
                    tag=f"ERROR waiting for {actor.node.alias} client connect",
                )
            if hasattr(actor, "gw_client"):
                wait_for(
                    actor.gw_client.is_connected,
                    1,
                    "ERROR waiting for gw_client connect",
                )
        scada._scada_atn_fast_dispatch_contract_is_alive_stub = True
        atn.turn_on(ShNode.by_alias["a.elt1.relay"])
        wait_for(lambda: elt_relay.relay_state == 1, 10, f"Relay state {elt_relay.relay_state}")
        atn.status()
        wait_for(
            lambda: atn.cli_resp_received > 0, 10, f"cli_resp_received == 0 {atn.summary_str()}"
        )

        wait_for(
            lambda: len(ear.num_received_by_topic) > 0, 10, f"ear receipt. {ear.summary_str()}"
        )

        topic = f"{scada.atn_g_node_alias}/{GtDispatchBoolean_Maker.type_alias}"
        print(topic)
        wait_for(
            lambda: ear.num_received_by_topic[topic] > 0, 10, f"ear receipt. {ear.summary_str()}"
        )
        assert ear.num_received_by_topic[topic] > 0

        wait_for(
            lambda: scada.num_received_by_topic["a.elt1.relay/gt.telemetry.110"] > 0,
            10,
            f"scada elt telemetry. {scada.summary_str()}",
        )

        # wait_for(lambda: scada.num_received_by_topic["a.m/p"] > 0, 10, f"scada power. {scada.summary_str()}")
        # This should report after turning on the relay. But that'll take a simulated element
        # that actually turns on and can be read by the simulated power meter

        wait_for(
            lambda: scada.num_received_by_topic["a.tank.temp0/gt.telemetry.110"] > 0,
            10,
            f"scada temperature. {scada.summary_str()}",
        )

        atn.turn_off(ShNode.by_alias["a.elt1.relay"])
        wait_for(
            lambda: int(elt_relay.relay_state) == 0, 10, f"Relay state {elt_relay.relay_state}"
        )

    finally:
        for actor in actors:
            # noinspection PyBroadException
            try:
                actor.stop()
            except:
                pass
