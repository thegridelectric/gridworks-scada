"""`gws layout` — hardware layout commands.

Only inspection lives here. Layout *generation* is tlayouts' job: a home's
layout is authored there as a sema layout word and copied onto the box, so
this repo reads layouts and never writes them.
"""

from typing import Annotated

import typer

import show_layout

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="GridWorks hardware layout tools.",
)


@app.command()
def show(
    env_file: str = ".env",
    layout_file: Annotated[
        str, typer.Option(
            "--layout-file", "-l",
            help=(
                "Name of layout file (e.g. hardware-layout.json or apple for apple.json). "
                "If path is relative it will be relative to settings.paths.config_dir. "
                "If path has no extension, .json will be assumed. "
                "If not specified default settings.paths.hardware_layout will be used."
            ),
        )
    ] = "",
    ops_file: Annotated[
        str, typer.Option(
            "--ops-file", "-o",
            help=(
                "Name of the operational-params file. Resolved like --layout-file. "
                "If not specified the file beside the layout is used."
            ),
        )
    ] = "",
    raise_errors: Annotated[
        bool, typer.Option(
            "--raise-errors",
            "-r",
            help="Raise any errors immediately to see full call stack."
        )
    ] = False,
    verbose: Annotated[
        bool, typer.Option(
            "--verbose",
            "-v",
            help="Print additional information"
        )
    ] = False,
    table_only: Annotated[
        bool, typer.Option(
            "--table-only",
            "-t",
            help="Print only the table"
        )
    ] = False,
):
    """Show hardware layout."""
    args = ["-e", env_file]
    if layout_file:
        args.extend(["-l", layout_file])
    if ops_file:
        args.extend(["-o", ops_file])
    if raise_errors:
        args.append("-r")
    if verbose:
        args.append("-v")
    if table_only:
        args.append("-t")
    show_layout.main(args)


@app.callback()
def _main() -> None: ...


# For sphinx:
typer_click_object = typer.main.get_command(app)

if __name__ == "__main__":
    app()
