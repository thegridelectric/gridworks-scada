import json

from gwproactor_test.certs import copy_keys, uses_tls
from pydantic import ValidationError

from actors import DerivedGenerator
from actors.codec_factories import ScadaMessageDecoder
from actors.config import ScadaSettings
from gwsproto.named_types import SendLayout
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp


def test_ha1_params_set_the_rswt_quadratic():
    scada_app = ScadaApp(app_settings=ScadaSettings())
    settings = scada_app.settings
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.mkdirs()
    scada_app.instantiate()
    derived = DerivedGenerator(CoreNodeNames.derived_generator, services=scada_app)

    assert set(derived.temperature_channel_names) == {
        'buffer-depth1', 'buffer-depth2', 'buffer-depth3',
        'hp-ewt', 'hp-lwt', 'dist-swt', 'dist-rwt',
        'buffer-cold-pipe', 'buffer-hot-pipe', 'store-cold-pipe', 'store-hot-pipe',
        'tank1-depth1', 'tank1-depth2', 'tank1-depth3',
    }

    assert derived.params.IntermediateRswtF == 100
    assert derived.params.IntermediatePowerKw == 1.5
    assert derived.params.DdRswtF == 150
    assert derived.params.DdPowerKw == 5.5
    assert derived.no_power_rswt == 55

    assert abs(derived.rswt_quadratic_params[0] - 0.0004912280701754388) < 0.000001
    assert abs(derived.rswt_quadratic_params[1] + 0.042807017543859696) < 0.00001
    assert abs(derived.rswt_quadratic_params[2] - 0.868421052631581) < 0.001

    # Intermediate kw and rswt match
    assert derived.required_swt(required_kw_thermal=1.5) == 100
    # design day kw and rswt match
    assert derived.required_swt(required_kw_thermal=5.5) == 150
    # try something hotter
    assert derived.required_swt(required_kw_thermal=8) == 171.7


def test_the_scada_does_not_decode_scada_params():
    """The scada's heating-curve parameters come from the operational
    params word. A scada.params message from the LTN is not a word the
    scada's decoder knows, so the link never dispatches one; a send.layout
    on the same path still decodes."""
    header = {"Src": "ltn", "Dst": "s", "MessageType": "scada.params"}
    params = {
        "FromGNodeAlias": "hw1.isone.me.versant.keene.spruce.ltn",
        "FromName": "ltn",
        "ToName": "s",
        "UnixTimeMs": 1792680900046,
        "MessageId": "cca1f682-fa05-422f-b789-08bee18fefc1",
        "TypeName": "scada.params",
        "Version": "005",
    }
    try:
        ScadaMessageDecoder.model_validate_json(json.dumps({"Header": header, "Payload": params}))
    except ValidationError:
        pass
    else:
        raise AssertionError("scada.params decoded")

    layout_request = SendLayout(
        FromGNodeAlias="hw1.isone.me.versant.keene.spruce.ltn",
        MessageCreatedMs=1792680900046,
    ).model_dump(by_alias=True)
    decoded = ScadaMessageDecoder.model_validate_json(
        json.dumps({"Header": {**header, "MessageType": "send.layout"}, "Payload": layout_request})
    )
    assert isinstance(decoded.Payload, SendLayout)
