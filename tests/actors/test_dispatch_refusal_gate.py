"""The dispatch gate: one derived answer, `Scada.dispatch_refusal`, read at
the offer. The precedence table as one test; then, over the in-process
LTN+scada pair, an offer refused for each reason gets `slow.contract.rejection`
with the reason and nothing else moves, and an accepted offer reaches the
family's ally."""

import time
import uuid
from pathlib import Path
from typing import Callable

import pytest
from gwproto import Message

from actors.scada import Scada
from gwsproto.enums import DispatchRefusalReason, MainAutoState, SlowDispatchContractStatus
from gwsproto.named_types import SlowContractHeartbeat, SlowContractRejection, SlowDispatchContract
from gwsproto.names.core.node_names import CoreNodeNames
from sema_to_dc import load_layout
from tests.actors.test_cold_handling import heating_ops, hold, make_app
from tests.utils.scada_live_test_helper import ScadaLiveTest, fresh_buffer

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}


# --- the precedence table ------------------------------------------------------

Prepare = Callable[[Scada], None]


def no_deed(scada: Scada) -> None:
    Path(scada.settings.paths.tadeed).unlink()


def nothing(scada: Scada) -> None:
    ...


ROWS: list[tuple[str, dict, Prepare, bool, DispatchRefusalReason | None]] = [
    # (id, ops changes, prepare, buffer fresh, reason)
    ("clean", {}, nothing, True, None),
    ("no-deed", {}, no_deed, True, DispatchRefusalReason.NoTaDeed),
    ("operator-hold", {"DispatchHold": hold(operator=True)}, nothing, True, DispatchRefusalReason.OperatorHold),
    ("broken", {"DispatchHold": hold(broken=True)}, nothing, True, DispatchRefusalReason.ServiceContractBroken),
    ("blind", {}, nothing, False, DispatchRefusalReason.ScadaBlind),
    # permanence wins: the deed over the hold, the hold over the sensing
    ("no-deed-over-hold", {"DispatchHold": hold(operator=True)}, no_deed, True, DispatchRefusalReason.NoTaDeed),
    ("hold-over-blind", {"DispatchHold": hold(broken=True)}, nothing, False, DispatchRefusalReason.ServiceContractBroken),
]


@pytest.mark.parametrize("row", ROWS, ids=[r[0] for r in ROWS])
@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_dispatch_refusal_follows_the_precedence_table(
    tmp_path: Path, pair: str, row: tuple[str, dict, Prepare, bool, DispatchRefusalReason | None]
) -> None:
    _, changes, prepare, fresh, reason = row
    ops_path = heating_ops(tmp_path, PAIRS[pair], **changes)
    scada = make_app(PAIRS[pair], ops_path).scada
    if fresh:
        fresh_buffer(scada)
    prepare(scada)
    assert scada.dispatch_refusal == reason
    status = scada.house_operating_status
    assert status.AcceptsDispatch is (reason is None)
    assert status.DispatchRefusalReason == reason
    assert status.ScadaBlind is (not fresh)


# --- offers over the LTN+scada pair --------------------------------------------


def offer(ltn) -> SlowContractHeartbeat:
    start_s = (int(time.time()) // 300) * 300 + 300
    return SlowContractHeartbeat(
        FromNode=ltn.node.name,
        Contract=SlowDispatchContract(
            ScadaAlias=ltn.layout.scada_g_node_alias,
            StartS=start_s,
            DurationMinutes=60,
            AvgPowerWatts=1000,
            OilBoilerOn=False,
            ContractId=str(uuid.uuid4()),
        ),
        Status=SlowDispatchContractStatus.Created,
        MessageCreatedMs=int(time.time() * 1000),
        MyDigit=5,
        YourLastDigit=None,
    )


def send_offer(ltn) -> SlowContractHeartbeat:
    hb = offer(ltn)
    ltn.contract_handler.latest_hb = hb
    ltn.services.send_threadsafe(
        Message(Src=ltn.node.name, Dst=CoreNodeNames.primary_scada, Payload=hb)
    )
    return hb


REFUSALS = [
    DispatchRefusalReason.NoTaDeed,
    DispatchRefusalReason.OperatorHold,
    DispatchRefusalReason.ServiceContractBroken,
    DispatchRefusalReason.ScadaBlind,
]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", REFUSALS, ids=[r.value for r in REFUSALS])
@pytest.mark.parametrize("pair", sorted(PAIRS))
async def test_a_refused_offer_gets_a_rejection_and_nothing_moves(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pair: str,
    reason: DispatchRefusalReason,
) -> None:
    layout_file, ops_file = PAIRS[pair]
    changes: dict = {}
    if reason is DispatchRefusalReason.OperatorHold:
        changes["DispatchHold"] = hold(operator=True)
    elif reason is DispatchRefusalReason.ServiceContractBroken:
        changes["DispatchHold"] = hold(broken=True)
    ops_path = heating_ops(tmp_path, (layout_file, ops_file), **changes)
    layout = load_layout(CONFIG / layout_file, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as tst:
        if reason is DispatchRefusalReason.NoTaDeed:
            Path(tst.child1_app.settings.paths.tadeed).unlink()
        tst.start_child1()
        scada = tst.child1_app.scada
        if reason is DispatchRefusalReason.ScadaBlind:
            # The simulated picos keep the buffer fresh here; blind the
            # scada at the predicate (the predicate itself is the unit test above).
            monkeypatch.setattr(Scada, "buffer_fresh", lambda self: False)
        tst.start_parent()
        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link",
        )
        ltn = tst.parent_app.ltn
        await tst.await_for(
            lambda: ltn.operating_status is not None
            and ltn.operating_status.DispatchRefusalReason == reason,
            "ERROR waiting for the LTN to see the refusal on the operating status",
            err_str_f=lambda: f"status: {ltn.operating_status}",
        )
        assert ltn.accepts_dispatch is False
        auto_state = MainAutoState.LocalControl
        assert scada.auto_state == auto_state
        prev_before = scada.contract_handler.prev

        rejections: list[SlowContractRejection] = []
        ltn_process = ltn.contract_handler.process_slow_contract_rejection

        def record(rejection: SlowContractRejection) -> None:
            rejections.append(rejection)
            ltn_process(rejection)

        monkeypatch.setattr(ltn.contract_handler, "process_slow_contract_rejection", record)

        for _ in range(2):  # the next price gets the same answer
            hb = send_offer(ltn)
            await tst.await_for(
                lambda: len(rejections) == len([r for r in rejections]) and any(
                    r.ContractId == hb.Contract.ContractId for r in rejections
                ),
                "ERROR waiting for the LTN to receive the rejection",
            )
            [rejection] = [r for r in rejections if r.ContractId == hb.Contract.ContractId]
            assert rejection.Reason == reason
            assert ltn.contract_handler.latest_hb is None
            assert scada.contract_handler.latest_scada_hb is None
            assert scada.contract_handler.prev is prev_before
            assert scada.auto_state == auto_state


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", sorted(PAIRS))
async def test_an_accepted_offer_reaches_the_ally(
    request: pytest.FixtureRequest, tmp_path: Path, pair: str
) -> None:
    layout_file, ops_file = PAIRS[pair]
    ops_path = heating_ops(tmp_path, (layout_file, ops_file))
    layout = load_layout(CONFIG / layout_file, ops_path)
    async with ScadaLiveTest(request=request, layout=layout, ops_path=ops_path) as tst:
        tst.start_child1()
        scada = tst.child1_app.scada
        tst.start_parent()
        await tst.await_for(
            lambda: tst.child_to_parent_link.active(),
            "ERROR waiting for scada to ltn link",
        )
        ltn = tst.parent_app.ltn
        await tst.await_for(
            lambda: ltn.operating_status is not None and ltn.accepts_dispatch,
            "ERROR waiting for the LTN to see the scada accepting dispatch",
            err_str_f=lambda: f"status: {ltn.operating_status}",
        )
        hb = send_offer(ltn)
        await tst.await_for(
            lambda: scada.contract_handler.latest_scada_hb is not None
            and scada.contract_handler.latest_scada_hb.Contract.ContractId == hb.Contract.ContractId,
            "ERROR waiting for the scada to take the offer",
        )
        assert scada.auto_state == MainAutoState.LeafTransactiveNode
