"""The BidRunner is one FLO run in one child process. Stop kills the
child and the thread ends, so a stop while a FLO is in flight does not
outlive systemd's timeout."""

import logging
import multiprocessing
import threading
import time

from actors.ltn.ltn import BidRunner
from gwproactor.message import PatInternalWatchdogMessage
from tests.actors.test_flo_request import build, ops


def sleeping_worker(flo_params_bytes: bytes, result_queue: multiprocessing.Queue) -> None:
    time.sleep(600)


def test_stop_kills_the_child_and_ends_the_run() -> None:
    sent = []
    completed = threading.Event()
    runner = BidRunner(
        params=build(),
        ops=ops(),
        io_loop_manager_name="io",
        ltn_name="ltn",
        ltn_g_node_alias="hw1.isone.me.versant.keene.oak",
        send_threadsafe=sent.append,
        on_complete=lambda name: completed.set(),
        logger=logging.getLogger("test-bid-runner"),
        worker=sleeping_worker,
    )
    runner.start()
    deadline = time.time() + 20
    while runner.child is None or not runner.child.is_alive():
        assert time.time() < deadline, "child never started"
        time.sleep(0.05)
    child = runner.child
    runner.stop()
    runner.join(timeout=15)
    assert not runner.is_alive()
    assert completed.is_set()
    assert not child.is_alive()
    assert all(isinstance(m, PatInternalWatchdogMessage) for m in sent), [type(m).__name__ for m in sent]
