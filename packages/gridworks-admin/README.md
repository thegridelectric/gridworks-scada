# gridworks-admin

This package contains gridworks-admin CLI tool for use in monitoring 
[gridworks-scada] devices. 

Install for the current user with:

```shell
uv tool install gridworks-admin
```

and then run the admin with:

```shell
gwa watch
```

Create a new configuration file with

```shell
gwa mkconfig
```

To see how to add a scada run:

```shell
gwa add-scada --help
```

The configuration file can viewed and edited manually with:
```shell
open `gwa config-file`
```

Configruation can be viewed from the command line with: 
```shell
gwa config
```

Top-level configuration can be modified on the command line with: 
```
gwa config --save [OPTIONS]
```

Scada configuration can be modified on the command line with:
```
gwa add-scada --update [OPTIONS] SCADA_SHORT_NAME
```
