"""Test HomeAlone w strategy ha1"""
import uuid
import time
from pathlib import Path

from gwproactor_test.certs import uses_tls
from gwproactor_test.certs import copy_keys

from actors import Scada
from actors import SynthGenerator
from actors.config import ScadaSettings
from data_classes.house_0_layout import House0Layout
from data_classes.house_0_names import H0N
from named_types import ScadaParams

def test_ha1(monkeypatch, tmp_path):
    # change to test directory and create an empty .env
    # so that 'find_dotenv()' in _scada_params_received() does not
    # modify any non-tests .envs in the file system.
    monkeypatch.chdir(tmp_path)
    dotenv_filepath = Path(".env")
    dotenv_filepath.touch()
    print(dotenv_filepath.absolute())
    import os
    print(os.getcwd())
    settings = ScadaSettings()
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.mkdirs()
    layout = House0Layout.load(settings.paths.hardware_layout)
    s = Scada(H0N.primary_scada, settings=settings, hardware_layout=layout)
    synth = SynthGenerator(H0N.synth_generator, services=s)

    assert set(synth.temperature_channel_names) == {
        'buffer-depth1', 'buffer-depth2', 'buffer-depth3', 'buffer-depth4', 
        'hp-ewt', 'hp-lwt', 'dist-swt', 'dist-rwt',
        'buffer-cold-pipe', 'buffer-hot-pipe', 'store-cold-pipe', 'store-hot-pipe',
        'tank1-depth1', 'tank1-depth2', 'tank1-depth3', 'tank1-depth4', 
        'tank2-depth1', 'tank2-depth2', 'tank2-depth3', 'tank2-depth4', 
        'tank3-depth1', 'tank3-depth2', 'tank3-depth3', 'tank3-depth4'
    }


    # test initial calc of quadratic params
    assert synth.params.IntermediateRswtF == 100
    assert synth.params.IntermediatePowerKw == 1.5
    assert synth.params.DdRswtF == 150
    assert synth.params.DdPowerKw == 5.5
    assert synth.no_power_rswt == 55


    assert abs(synth.rswt_quadratic_params[0] - 0.0004912280701754388) < 0.000001
    assert abs(synth.rswt_quadratic_params[1] + 0.042807017543859696) < 0.00001
    assert abs(synth.rswt_quadratic_params[2] - 0.868421052631581) < 0.001
    
    # Intermediate kw and rswt match
    assert synth.required_swt(required_kw_thermal=1.5) == 100
    # design day kw and rswt match
    assert synth.required_swt(required_kw_thermal=5.5) == 150
    # try something hotter
    assert synth.required_swt(required_kw_thermal=8) == 171.7

    # test getting new params from atn, resulting in new rswt quad params
    new = synth.params.model_copy(update={"DdPowerKw": 10})
    params_from_atn = ScadaParams(
        FromGNodeAlias=synth.layout.atn_g_node_alias,
        FromName=H0N.atn,
        ToName=H0N.primary_scada,
        UnixTimeMs=int(time.time() * 1000),
        MessageId=str(uuid.uuid4()),
        NewParams=new

    )

    s.scada_params_received(s.atn, params_from_atn, testing=True)
    assert synth.params.DdPowerKw == 10

    # wrote the new parameter to .env
    with open(dotenv_filepath, 'r') as file:
        lines = file.readlines()
    assert "SCADA_DD_POWER=10\n" in lines

    # this changes required_swt etc
    assert synth.required_swt(required_kw_thermal=5.5) == 128.7

    # Todo: validate scada sends out ScadaParams message with
    # correct new params

    # Todo: test missing various temperatures

    # Todo: test Scada entering/leaving Homealone

   

