import uuid
import time
from pathlib import Path

from gwproactor_test.certs import uses_tls
from gwproactor_test.certs import copy_keys

from actors import DerivedGenerator
from actors.config import ScadaSettings
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.named_types import ScadaParams
from scada_app import ScadaApp

def test_ha1(monkeypatch, tmp_path):
    # change to test directory and create an empty .env
    # so that 'find_dotenv()' in process_scada_params() does not
    # modify any non-tests .envs in the file system.
    monkeypatch.chdir(tmp_path)
    dotenv_filepath = Path(".env")
    dotenv_filepath.touch()
    print(dotenv_filepath.absolute())
    import os
    print(os.getcwd())
    scada_app = ScadaApp(app_settings=ScadaSettings(is_simulated=True))
    settings = scada_app.settings
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.mkdirs()
    scada_app.instantiate()
    s = scada_app.scada
    derived = DerivedGenerator(H0N.derived_generator, services=scada_app)

    assert set(derived.temperature_channel_names) == {
        'buffer-depth1', 'buffer-depth2', 'buffer-depth3',
        'hp-ewt', 'hp-lwt', 'dist-swt', 'dist-rwt',
        'buffer-cold-pipe', 'buffer-hot-pipe', 'store-cold-pipe', 'store-hot-pipe',
        'tank1-depth1', 'tank1-depth2', 'tank1-depth3',
        'tank2-depth1', 'tank2-depth2', 'tank2-depth3', 
        'tank3-depth1', 'tank3-depth2', 'tank3-depth3',
    }


    # test initial calc of quadratic params
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

    # test getting new params from ltn, resulting in new rswt quad params
    new = derived.params.model_copy(update={"DdPowerKw": 10})
    params_from_ltn = ScadaParams(
        FromGNodeAlias=derived.layout.ltn_g_node_alias,
        FromName=H0N.ltn,
        ToName=H0N.primary_scada,
        UnixTimeMs=int(time.time() * 1000),
        MessageId=str(uuid.uuid4()),
        NewParams=new

    )

    s.process_scada_params(s.ltn, params_from_ltn, testing=True)
    assert derived.params.DdPowerKw == 10

    # wrote the new parameter to .env
    with open(dotenv_filepath, 'r') as file:
        lines = file.readlines()
    assert "SCADA_DD_POWER=10\n" in lines

    # this changes required_swt etc
    assert derived.required_swt(required_kw_thermal=5.5) == 128.7

    # Todo: validate scada sends out ScadaParams message with
    # correct new params

    # Todo: test missing various temperatures

    # Todo: test Scada entering/leaving LocalControl

   

