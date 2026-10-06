"""The operating status is sent to the LTN once at startup and then only
when one of its fields changes: the top state as admin takes and releases
the tree, LtnDispatching from a contract's first Active heartbeat until
no contract has been active past a completion's warning window, the
validation state when the deed changes. A repeated report with nothing
changed sends nothing. In-process on every Standby x ServiceMode cell the
loader selects; a Standby cell refuses the offer and never dispatches."""

import json
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from actors.contract_handler import ContractHandler
from actors.leaf_ally_loader import LeafAlly
from actors.scada import Scada
from gwsproto.enums import (
    MainAutoState,
    SlowDispatchContractStatus,
    TaValidationState,
    TopState,
    TurnHpOnOff,
)
from gwsproto.named_types import (
    AdminDispatch,
    AdminReleaseControl,
    AllyGivesUp,
    FsmEvent,
    HouseOperatingStatus,
    SlowContractHeartbeat,
    SlowDispatchContract,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from sema_to_dc import load_layout
from tests.actors.test_relays_boot import CONFIG, LAYOUTS, ROWS, Row, row_ops
from tests.utils.scada_live_test_helper import ScadaLiveTest

# One row per (Standby, ServiceMode) cell of the selection table.
CELLS: dict[tuple[bool, str], Row] = {}
for _row in ROWS:
    CELLS.setdefault((_row.local_control.standby, _row.local_control.service), _row)
CELL_ROWS = tuple(CELLS.values())


async def no_announcer(self: Scada) -> None:
    """Stands in for the announcer task, so the test's own call is the only
    startup send."""


def fields(status: HouseOperatingStatus) -> dict[str, Any]:
    return status.model_dump(exclude={"UnixMs"})


def assert_only_changed(before: HouseOperatingStatus, after: HouseOperatingStatus, **changed: Any) -> None:
    """The later status differs from the earlier in exactly the named fields."""
    expected = {**fields(before), **changed}
    assert fields(after) == expected


# The end the scada's contract timing sees for each test contract, a few
# seconds after its creation: a contract is created on the next five-minute
# slot (heartbeat axiom 1) and lasts whole minutes, so its real end is too
# far off for a test to wait on.
ENDS: dict[str, int] = {}
SECONDS_TO_END = 2
# The warning and grace windows after a contract's end, as fractions of a
# minute: 3 s and 6 s. A second contract created inside the warning window
# is back to back with the first.
WARNING_MINUTES = 0.05
GRACE_MINUTES = 0.1


def patched_end_s(self: SlowDispatchContract) -> int:
    return ENDS.get(self.ContractId, self.StartS + self.DurationMinutes * 60)


def new_contract(scada: Scada) -> SlowDispatchContract:
    """A contract on the next five-minute slot, ending SECONDS_TO_END from now
    as far as the scada's timing is concerned."""
    contract = SlowDispatchContract(
        ScadaAlias=scada.layout.scada_g_node_alias,
        StartS=(int(time.time()) // 300) * 300 + 300,
        DurationMinutes=60,
        AvgPowerWatts=1000,
        OilBoilerOn=False,
        ContractId=str(uuid.uuid4()),
    )
    ENDS[contract.ContractId] = int(time.time()) + SECONDS_TO_END
    return contract


def ltn_hb(scada: Scada, contract: SlowDispatchContract, status: SlowDispatchContractStatus) -> SlowContractHeartbeat:
    return SlowContractHeartbeat(
        FromNode=scada.ltn.name,
        Contract=contract,
        Status=status,
        Cause="test" if status == SlowDispatchContractStatus.CompletedUnknownOutcome else None,
        MessageCreatedMs=int(time.time() * 1000),
        MyDigit=5,
        YourLastDigit=None,
    )


def admin_turn_on() -> AdminDispatch:
    return AdminDispatch(
        DispatchTrigger=FsmEvent(
            FromHandle=CoreNodeNames.admin,
            ToHandle=f"{CoreNodeNames.admin}.{HSNN.hp_boss}",
            EventType=TurnHpOnOff.enum_name(),
            EventName=TurnHpOnOff.TurnOn,
            SendTimeUnixMs=int(time.time() * 1000),
            TriggerId=str(uuid.uuid4()),
        ),
        TimeoutSeconds=120,
    )


def swap_deed(scada: Scada) -> TaValidationState:
    """Rewrite the deed with another validation state; return it."""
    path = Path(scada.settings.paths.tadeed)
    deed = json.loads(path.read_text())
    other = next(
        s for s in TaValidationState
        if s not in (TaValidationState(deed["ValidationState"]), TaValidationState.UnValidated)
    )
    deed["ValidationState"] = other.value
    path.write_text(json.dumps(deed))
    return other


async def walk_contract(h: ScadaLiveTest, scada: Scada, to_ltn: list[Any]) -> SlowDispatchContract:
    """Created -> Received (the ally suits up) -> Active -> Completed."""
    contract = new_contract(scada)
    scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
    await h.await_for(
        lambda: any(
            isinstance(p, SlowContractHeartbeat)
            and p.Contract.ContractId == contract.ContractId
            and p.Status == SlowDispatchContractStatus.Received
            for p in to_ltn
        ),
        "ERROR waiting for the scada's Received heartbeat",
        err_str_f=lambda: (
            f"to_ltn: {[type(p).__name__ for p in to_ltn]}\n"
            f"hbs: {[(p.Status, p.Contract.ContractId[:8], p.Cause) for p in to_ltn if isinstance(p, SlowContractHeartbeat)]}\n"
            f"glitches: {[(p.Summary, p.Details) for p in to_ltn if type(p).__name__ == 'Glitch']}\n"
            f"want: {contract.ContractId[:8]}\n"
            f"latest_scada_hb: {scada.contract_handler.latest_scada_hb}\n"
            f"auto_state: {scada.auto_state} validation: {scada.services.validation_state}"
        ),
    )
    assert scada.auto_state == MainAutoState.LeafTransactiveNode
    scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Active))
    assert scada.contract_handler.latest_scada_hb.Status == SlowDispatchContractStatus.Active
    # A completion before the end is refused; wait the few seconds out.
    await h.await_for(
        lambda: time.time() > ENDS[contract.ContractId],
        "ERROR waiting for the contract's end",
        timeout=SECONDS_TO_END + 5,
    )
    scada.process_scada_message(
        scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.CompletedUnknownOutcome)
    )
    assert scada.contract_handler.latest_scada_hb is None
    return contract


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row", CELL_ROWS, ids=[f"{r.layout}-standby{r.local_control.standby}-{r.local_control.service.value}" for r in CELL_ROWS]
)
async def test_operating_status_emits_once_per_change(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, row: Row
) -> None:
    monkeypatch.setattr(Scada, "announce_at_first_broker_link", no_announcer)
    monkeypatch.setattr(ContractHandler, "WARNING_MINUTES_AFTER_END", WARNING_MINUTES)
    monkeypatch.setattr(ContractHandler, "GRACE_PERIOD_MINUTES", GRACE_MINUTES)
    monkeypatch.setattr(SlowDispatchContract, "contract_end_s", patched_end_s)
    layout_file, ops_file = LAYOUTS[row.layout]
    ops_path = row_ops(tmp_path, ops_file, row)
    layout = load_layout(CONFIG / layout_file, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as h:
        h.start_child1()
        scada = h.child1_app.scada
        statuses: list[HouseOperatingStatus] = []
        to_ltn: list[Any] = []
        original_send = scada._send_to

        def record(to_node, payload, from_node=None):
            if isinstance(payload, HouseOperatingStatus):
                statuses.append(payload)
            if to_node == scada.ltn:
                to_ltn.append(payload)
            original_send(to_node, payload, from_node)

        monkeypatch.setattr(scada, "_send_to", record)
        # Startup: one status, the ops word's six facts plus the runtime ones.
        scada.send_startup_announcements()
        assert len(statuses) == 1
        first = statuses[0]
        ops = scada.ops
        assert fields(first) == {
            "ScadaAlias": scada.layout.scada_g_node_alias,
            "ValidationState": h.child1_app.validation_state,
            "Standby": ops.Standby,
            "StandbyPosture": ops.StandbyPosture,
            "SeasonalStorageMode": ops.FamilyParams.SeasonalStorageMode,
            "ServiceMode": ops.ServiceMode,
            "AcceptsDispatch": ops.AcceptsDispatch,
            "DispatchRefusalReason": ops.DispatchRefusalReason,
            "TopState": TopState.Auto,
            "LtnDispatching": False,
            "TypeName": "gw.house.operating.status",
            "Version": "000",
        }
        assert first.Standby == row.local_control.standby
        assert first.ServiceMode == row.local_control.service

        # Nothing changed: nothing sent.
        for _ in range(3):
            scada.report_operating_status()
        assert len(statuses) == 1

        # Admin takes the tree and releases it: TopState alone moves.
        scada.process_scada_message(scada.admin, admin_turn_on())
        assert len(statuses) == 2
        assert_only_changed(statuses[0], statuses[1], TopState=TopState.Admin)
        scada.process_scada_message(scada.admin, AdminReleaseControl())
        assert len(statuses) == 3
        assert_only_changed(statuses[1], statuses[2], TopState=TopState.Auto)
        await h.await_for(
            lambda: scada.auto_state == MainAutoState.LocalControl,
            "ERROR waiting for auto to wake into LocalControl",
        )

        if ops.AcceptsDispatch:
            # Two contracts back to back: LtnDispatching rises on the first
            # Active heartbeat, holds through the completion and the second
            # contract, and falls once the second has ended with no new one
            # past the warning window.
            await walk_contract(h, scada, to_ltn)
            assert len(statuses) == 4
            assert_only_changed(statuses[2], statuses[3], LtnDispatching=True)
            await walk_contract(h, scada, to_ltn)
            assert len(statuses) == 4
            await h.await_for(
                lambda: len(statuses) == 5,
                "ERROR waiting for LtnDispatching to fall after the second contract's end",
                timeout=SECONDS_TO_END + WARNING_MINUTES * 60 + 10,
                err_str_f=lambda: f"to_ltn: {[type(p).__name__ for p in to_ltn]}",
            )
            assert_only_changed(statuses[3], statuses[4], LtnDispatching=False)
        else:
            # Standby refuses the offer: the wrapper gives up, nothing is sent.
            la = scada.services.get_communicator_as_type(CoreNodeNames.leaf_ally, LeafAlly)
            assert la is not None
            given_up: list[AllyGivesUp] = []
            ally_send = la._send_to

            def record_ally(dst, payload, src=None):
                if isinstance(payload, AllyGivesUp):
                    given_up.append(payload)
                ally_send(dst, payload, src)

            monkeypatch.setattr(la, "_send_to", record_ally)
            contract = new_contract(scada)
            scada.process_scada_message(scada.ltn, ltn_hb(scada, contract, SlowDispatchContractStatus.Created))
            await h.await_for(
                lambda: bool(given_up) and scada.auto_state == MainAutoState.LocalControl,
                "ERROR waiting for the wrapper's AllyGivesUp and the fall back to LocalControl",
            )
            assert scada.contract_handler.latest_scada_hb is None
            assert len(statuses) == 3

        # The deed changes: the next report carries the new validation state.
        before = statuses[-1]
        other = swap_deed(scada)
        count = len(statuses)
        scada.report_operating_status()
        assert len(statuses) == count + 1
        assert_only_changed(before, statuses[-1], ValidationState=other)
