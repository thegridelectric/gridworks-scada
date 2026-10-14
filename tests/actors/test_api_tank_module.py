"""The tank-module actor's liveness rule: when a pico is missing and how
often that is reported."""

import time

from gwproactor_test.certs import copy_keys, uses_tls

from actors.api_tank_module import ApiTankModule, FLATLINE_REPORT_S, NYQUIST_MULTIPLE
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.named_types import PicoMissing
from scada_app import ScadaApp


def buffer_actor() -> ApiTankModule:
    settings = ScadaApp.get_settings()
    settings.is_simulated = True
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return ApiTankModule(H0N.buffer.reader, services=scada_app)


def test_post_late_by_a_second_is_not_missing():
    actor = buffer_actor()
    period = actor.flatline_seconds()
    assert period == 60
    actor.last_heard = time.time() - (period + 0.8)
    assert not actor.missing()


def test_silence_past_the_margin_is_missing():
    actor = buffer_actor()
    bound = NYQUIST_MULTIPLE * actor.flatline_seconds()
    actor.last_heard = time.time() - (bound - 1)
    assert not actor.missing()
    actor.last_heard = time.time() - (bound + 1)
    assert actor.missing()


def test_missing_report_repeats_on_its_own_period(monkeypatch):
    actor = buffer_actor()
    sent: list = []
    monkeypatch.setattr(actor, "_send_to", lambda dst, payload, src=None: sent.append(payload))
    actor.last_heard = time.time() - 10 * actor.flatline_seconds()
    actor.last_error_report = time.time() - FLATLINE_REPORT_S - 1
    assert actor.report_missing_if_due()
    assert len([p for p in sent if isinstance(p, PicoMissing)]) == 1
    assert not actor.report_missing_if_due()
    assert len([p for p in sent if isinstance(p, PicoMissing)]) == 1
    actor.last_error_report = time.time() - FLATLINE_REPORT_S - 1
    assert actor.report_missing_if_due()
    assert len([p for p in sent if isinstance(p, PicoMissing)]) == 2
    actor.last_heard = time.time()
    actor.last_error_report = time.time() - FLATLINE_REPORT_S - 1
    assert not actor.report_missing_if_due()
