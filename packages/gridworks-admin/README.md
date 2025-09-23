# gridworks-admin

This package contains gridworks-admin CLI tool for use in monitoring gridworks-scada
devices. 

Install for the current user with:

```
uv tool install gridworks-admin
```

and then run the admin with:

```
gwa watch
```

Create a new configuration file with

```
gwa mkconfig
```

To see how to add a scada do

```
gwa add-scada --help
```

Edit the config file manually with

```
open `gwa config-file`
```


The tool can be run ephemerally with:
```
uvx --from gridworks-admin gwa
```


Or from the repo by re-creating the environment:

```
tools/mkenv.sh
source gw_spaceheat/venv/bin/activate
gwa
```

