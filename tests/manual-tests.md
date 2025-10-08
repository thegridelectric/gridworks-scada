# Matrix of execution environments to test

pytest / CI attempts to catch as much if this as possible, but running on a Pi
and using the repl makes this tricky and some manual testing is required. 

| Runnable        | MacOS | Pi | cloud | 
|-----------------|-------|----|-------|
| gws run         |       |    |       |
| scada/repl      |       |    |       |
| gws atn run     |       |    |       |
| atn in repl     |       |    |       |
| gwa watch       |       |    |       |
| uvx admin       |       |    |       |
| service         |   -   |    |   -   |


## Scada repl code
```python
from scada_app import ScadaApp
from actors.config import ScadaSettings
import dotenv
app = ScadaApp.make_app_for_cli(app_settings=ScadaSettings(_env_file=dotenv.find_dotenv())) # noqa
app.run_in_thread()
s = app.prime_actor
```


### Atn repl code
```python
from actors.atn.atn_config import AtnSettings; from atn_app import AtnApp; import dotenv
a = AtnApp.get_repl_app(app_settings=AtnSettings(_env_file=dotenv.find_dotenv())).atn # noqa
```

### uvx command line

Note: correct the --env-file path

    uvx --from gridworks-admin gwa watch --env-file ABSOLUTE/PATH/TO/ACTUAL/.env