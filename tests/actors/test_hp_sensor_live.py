"""The heat-pump sensing chain on a running sim Nolan scada: the power
meter's hp-odu readings reach hp-sensor through its subscription, hp-sensor
reports its state, the state reaches the heating machine through its
subscription, and the secondary pump relay follows."""

import json
import typing
from pathlib import Path

import pytest

from actors.config import ScadaSettings
from actors.hp_sensor import HpSensor
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control_loader import LocalControl
from actors.power_meter import PowerMeter, PowerMeterDriverThread
from actors.relay import Relay
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import GridworksSimPm1_PowerMeterDriver
from gwsproto.enums import RelayClosedOrOpen, SeasonalStorageMode, ServiceMode, SpruceHackHpState
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from gwsproto.names.nolan.node_names import NolanNodeNames
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest

CONFIG = Path(__file__).parent.parent / "config"
NOLAN_LAYOUT = CONFIG / "gw.nolan.layout.json"
NOLAN_OPS = CONFIG / "gw.nolan.operational.params.json"


def heating_settings(tmp_path: Path, lost_after_s: float) -> ScadaSettings:
    """The sim Nolan pair with the heating machine selected and a power
    meter that calls a channel lost after lost_after_s."""
    ops = json.loads(NOLAN_OPS.read_text())
    ops["Standby"] = False
    ops["ServiceMode"] = ServiceMode.Heating.value
    ops["FamilyParams"]["SeasonalStorageMode"] = SeasonalStorageMode.BufferOnly.value
    ops_path = tmp_path / NOLAN_OPS.name
    ops_path.write_text(json.dumps(ops))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = NOLAN_LAYOUT
    settings.paths.operational_params = ops_path
    settings.power_meter_lost_after_s = lost_after_s
    return settings


@pytest.mark.asyncio
async def test_the_pump_follows_the_heat_pump_through_both_subscriptions(
    request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    settings = heating_settings(tmp_path, lost_after_s=1.0)
    async with ScadaLiveTest(
        request=request,
        child_app_settings=settings,
        ops_path=settings.paths.operational_params,
    ) as h:
        h.start_child1()
        app = h.child1_app
        scada = app.scada
        lc = app.get_communicator_as_type(CoreNodeNames.local_control, LocalControl)
        assert lc is not None
        heat = lc._impl
        assert isinstance(heat, NolanBufferOnlyTou)
        hp_sensor = app.get_communicator_as_type(HSNN.hp_sensor, HpSensor)
        pump = app.get_communicator_as_type(NolanNodeNames.secondary_pump_relay, Relay)
        meter = app.get_communicator_as_type(CoreNodeNames.asset_power_meter, PowerMeter)
        assert hp_sensor is not None and pump is not None and meter is not None
        driver = typing.cast(
            GridworksSimPm1_PowerMeterDriver,
            typing.cast(PowerMeterDriverThread, meter._sync_thread).driver,
        )

        def chain_at(state: SpruceHackHpState, pump_state: RelayClosedOrOpen) -> bool:
            latest = scada.data.latest_machine_state.get(HSNN.hp_sensor)
            return (
                hp_sensor.state == state
                and latest is not None
                and latest.State == state
                and heat.hp_state == state
                and pump.state == pump_state
            )

        def where() -> str:
            latest = scada.data.latest_machine_state.get(HSNN.hp_sensor)
            return (
                f"hp-sensor {hp_sensor.state}, scada holds {latest.State if latest else None}, "
                f"heating machine {heat.hp_state}, pump {pump.state}, "
                f"hp-odu-pwr {scada.data.latest_channel_values.get(HCN.hp_odu_pwr)}"
            )

        # The sim meter reads 0 W: the first read detects off and the pump stops.
        await h.await_for(
            lambda: chain_at(SpruceHackHpState.HpDetectedOff, RelayClosedOrOpen.RelayOpen),
            "0 W: HpDetectedOff and the pump off",
            timeout=10,
            err_str_f=where,
        )
        assert scada.channel_subscribers[HCN.hp_odu_pwr] == [HSNN.hp_sensor]
        assert scada.machine_state_subscribers[HSNN.hp_sensor] == [CoreNodeNames.local_control]

        driver.fake_power_w = 700
        await h.await_for(
            lambda: chain_at(SpruceHackHpState.HpDetectedOn, RelayClosedOrOpen.RelayClosed),
            "700 W: HpDetectedOn and the pump on",
            timeout=10,
            err_str_f=where,
        )

        driver.fake_power_w = 0
        await h.await_for(
            lambda: chain_at(SpruceHackHpState.HpDetectedOff, RelayClosedOrOpen.RelayOpen),
            "0 W again: HpDetectedOff and the pump off",
            timeout=10,
            err_str_f=where,
        )

        # The channel returns no value: lost after a second, Unknown, pump on.
        driver.no_value_channel_names = {HCN.hp_odu_pwr}
        await h.await_for(
            lambda: chain_at(SpruceHackHpState.Unknown, RelayClosedOrOpen.RelayClosed),
            "hp-odu-pwr lost: Unknown and the pump on",
            timeout=10,
            err_str_f=where,
        )
