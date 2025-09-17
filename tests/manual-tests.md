# Matrix of execution environments to test

pytest / CI attempts to catch as much if this as possible, but running on a Pi
and using the repl makes this tricky and some manual testing is required. 

| Runnable        | MacOS | Pi | cloud | 
|-----------------|-------|----|-------|
| gws run         |       |    |       |
| scada/repl      |       |    |       |
| gws atn run     |       |    |       |
| atn in repl     |       |    |       |
| gws admin watch |       |    |       |
| gwa watch       |       |    |       |
| uvx admin       |       |    |       |


## Scada repl code
```python
import typing
from scada_app import ScadaApp
from actors.config import ScadaSettings
import dotenv
ef = dotenv.find_dotenv()
settings = ScadaSettings(_env_file=ef)
app = typing.cast(ScadaApp, ScadaApp.make_app_for_cli(app_settings=settings, env_file=ef))
app.run_in_thread()
s = app.prime_actor
```


### Atn repl code
```python

```

### uvx command line

uvx --from gridworks-admin gwa watch --env-file ABSOLUTE/PATH/TO/ACTUAL/.env