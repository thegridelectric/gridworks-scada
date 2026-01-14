# Matrix of execution environments to test

pytest / CI attempts to catch as much if this as possible, but running on a Pi
and using the repl makes this tricky and some manual testing is required. 

| Runnable        | MacOS | Pi | cloud | 
|-----------------|-------|----|-------|
| gws run         |       |    |       |
| scada/repl      |       |    |       |
| gws ltn run     |       |    |       |
| ltn in repl     |       |    |       |
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


### Ltn repl code
```python
from actors.ltn.config import LtnSettings; from ltn_app import LtnApp; import dotenv
l = LtnApp.get_repl_app(app_settings=LtnSettings(_env_file=dotenv.find_dotenv())).ltn # noqa
```

### uvx command line

Note: correct the --env-file path

    uvx --from gridworks-admin gwa watch --env-file ABSOLUTE/PATH/TO/ACTUAL/.env