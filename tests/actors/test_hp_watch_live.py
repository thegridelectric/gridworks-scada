"""The heat-pump sensing chain on a running sim Nolan scada: the power
meter's hp-odu readings reach hp-watch through its subscription, hp-watch
reports its state, the state reaches the heating machine and hp-boss
through their subscriptions, and the secondary pump relay follows under
hp-boss (the call open throughout: the sim buffer reads full)."""

import time
import typing
import uuid
from pathlib import Path

import pytest

from actors.config import ScadaSettings
from actors.hp_boss import HpBoss
from actors.hp_watch import HpWatch
from actors.local_control.nolan.buffer_only_tou import NolanBufferOnlyTou
from actors.local_control_loader import LocalControl
from actors.power_meter import PowerMeter, PowerMeterDriverThread
from actors.relay import Relay
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import GridworksSimPm1_PowerMeterDriver
from gwsproto.enums import (
    HpBossState,
    RelayClosedOrOpen,
    SeasonalStorageMode,
    ServiceMode,
    SpruceHackHpState,
    TurnHpOnOff,
)
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, FsmEvent
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from gwsproto.names.nolan.node_names import NolanNodeNames
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ScadaLiveTest, ops_word_with

CONFIG = Path(__file__).parent.parent / "config"
NOLAN_LAYOUT = CONFIG / "gw.nolan.layout.json"
NOLAN_OPS = CONFIG / "gw.nolan.operational.params.json"


def heating_settings(tmp_path: Path, lost_after_s: float) -> ScadaSettings:
    """The sim Nolan pair with the heating machine selected and a power
    meter that calls a channel lost after lost_after_s."""
    ops_path = ops_word_with(
        NOLAN_OPS,
        tmp_path / NOLAN_OPS.name,
        standby=False,
        service_mode=ServiceMode.Heating,
        seasonal_storage_mode=SeasonalStorageMode.BufferOnly,
    )
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
        hp_watch = app.get_communicator_as_type(HSNN.hp_watch, HpWatch)
        pump = app.get_communicator_as_type(NolanNodeNames.secondary_pump_relay, Relay)
        meter = app.get_communicator_as_type(CoreNodeNames.asset_power_meter, PowerMeter)
        assert hp_watch is not None and pump is not None and meter is not None
        driver = typing.cast(
            GridworksSimPm1_PowerMeterDriver,
            typing.cast(PowerMeterDriverThread, meter._sync_thread).driver,
        )

        def chain_at(state: SpruceHackHpState, pump_state: RelayClosedOrOpen) -> bool:
            latest = scada.data.latest_machine_state.get(HSNN.hp_watch)
            return (
                hp_watch.state == state
                and latest is not None
                and latest.State == state
                and heat.hp_state == state
                and pump.state == pump_state
            )

        def where() -> str:
            latest = scada.data.latest_machine_state.get(HSNN.hp_watch)
            return (
                f"hp-watch {hp_watch.state}, scada holds {latest.State if latest else None}, "
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
        assert scada.channel_subscribers[HCN.hp_odu_pwr] == [HSNN.hp_watch]
        assert sorted(scada.machine_state_subscribers[HSNN.hp_watch]) == sorted(
            [CoreNodeNames.local_control, HSNN.hp_boss]
        )
        assert pump.node.handle == f"{scada.layout.hp_boss.handle}.{NolanNodeNames.secondary_pump_relay}"

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


def admin_turn(name: TurnHpOnOff) -> AdminDispatch:
    """The admin client's wire shape: it addresses hp-boss under admin."""
    return AdminDispatch(
        DispatchTrigger=FsmEvent(
            FromHandle=CoreNodeNames.admin,
            ToHandle=f"{CoreNodeNames.admin}.{HSNN.hp_boss}",
            EventType=TurnHpOnOff.enum_name(),
            EventName=name,
            SendTimeUnixMs=int(time.time() * 1000),
            TriggerId=str(uuid.uuid4()),
        ),
        TimeoutSeconds=120,
    )


@pytest.mark.asyncio
async def test_under_admin_the_pump_follows_the_heat_pumps_power_not_the_call(
    request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """Admin takes the tree and turns the heat pump on through hp-boss: the
    call relay closes and the pump stays off, the unit sensed off at 0 W.
    The sim meter then reads 700 W, hp-watch senses the unit on and
    hp-boss starts the pump. Admin opens the call: the pump keeps running
    until the meter reads 0 W and the watch senses the unit off."""
    settings = heating_settings(tmp_path, lost_after_s=1.0)
    async with ScadaLiveTest(
        request=request,
        child_app_settings=settings,
        ops_path=settings.paths.operational_params,
    ) as h:
        h.start_child1()
        app = h.child1_app
        scada = app.scada
        hp_boss = app.get_communicator_as_type(HSNN.hp_boss, HpBoss)
        hp_watch = app.get_communicator_as_type(HSNN.hp_watch, HpWatch)
        pump = app.get_communicator_as_type(NolanNodeNames.secondary_pump_relay, Relay)
        call = app.get_communicator_as_type(HSNN.hp_scada_ops_relay, Relay)
        meter = app.get_communicator_as_type(CoreNodeNames.asset_power_meter, PowerMeter)
        assert hp_boss is not None and hp_watch is not None
        assert pump is not None and call is not None and meter is not None
        driver = typing.cast(
            GridworksSimPm1_PowerMeterDriver,
            typing.cast(PowerMeterDriverThread, meter._sync_thread).driver,
        )

        def at(hp: SpruceHackHpState, pump_state: RelayClosedOrOpen, call_state: RelayClosedOrOpen) -> bool:
            return hp_watch.state == hp and pump.state == pump_state and call.state == call_state

        def where() -> str:
            return (
                f"hp-watch {hp_watch.state}, hp-boss {hp_boss.state}, call {call.state}, "
                f"pump {pump.state}, hp-odu-pwr {scada.data.latest_channel_values.get(HCN.hp_odu_pwr)}"
            )

        # 0 W from the sim meter: the unit sensed off, the pump off, the call open.
        await h.await_for(
            lambda: at(SpruceHackHpState.HpDetectedOff, RelayClosedOrOpen.RelayOpen, RelayClosedOrOpen.RelayOpen),
            "0 W: HpDetectedOff, pump off, call open",
            timeout=10,
            err_str_f=where,
        )

        # Admin turns the heat pump on through hp-boss: the call closes, the pump does not.
        scada.process_scada_message(scada.admin, admin_turn(TurnHpOnOff.TurnOn))
        assert hp_boss.node.handle == f"{CoreNodeNames.admin}.{HSNN.hp_boss}"
        assert pump.node.handle == f"{hp_boss.node.handle}.{NolanNodeNames.secondary_pump_relay}"
        await h.await_for(
            lambda: hp_boss.state == HpBossState.HpOn and call.state == RelayClosedOrOpen.RelayClosed,
            "admin TurnOn: hp-boss HpOn and the call closed",
            timeout=10,
            err_str_f=where,
        )
        assert pump.state == RelayClosedOrOpen.RelayOpen

        # The unit answers the call: power up, the watch senses on, hp-boss starts the pump.
        driver.fake_power_w = 700
        await h.await_for(
            lambda: at(SpruceHackHpState.HpDetectedOn, RelayClosedOrOpen.RelayClosed, RelayClosedOrOpen.RelayClosed),
            "700 W under admin: HpDetectedOn and the pump on",
            timeout=10,
            err_str_f=where,
        )

        # Admin opens the call: the unit still draws power, so the pump keeps running.
        scada.process_scada_message(scada.admin, admin_turn(TurnHpOnOff.TurnOff))
        await h.await_for(
            lambda: hp_boss.state == HpBossState.HpOff and call.state == RelayClosedOrOpen.RelayOpen,
            "admin TurnOff: hp-boss HpOff and the call open",
            timeout=10,
            err_str_f=where,
        )
        assert pump.state == RelayClosedOrOpen.RelayClosed

        # The unit winds down: the watch senses off and the pump stops.
        driver.fake_power_w = 0
        await h.await_for(
            lambda: at(SpruceHackHpState.HpDetectedOff, RelayClosedOrOpen.RelayOpen, RelayClosedOrOpen.RelayOpen),
            "0 W under admin: HpDetectedOff and the pump off",
            timeout=10,
            err_str_f=where,
        )
        scada.process_scada_message(scada.admin, AdminReleaseControl())
