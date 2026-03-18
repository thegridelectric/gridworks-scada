"""layout generation command-line interface."""
from typing import Annotated

import typer
from pathlib import Path

import show_layout
from layout_gen.tst import make_tst_layout

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    help="GridWorks hardware layout tools.",
)

@app.command()
def mktest(
    tag: str = "test",
    write: bool = True,
    src: Path = Path("tests/config/hardware-layout.json")
) -> None:
    """Generate the hardware layout file used by tests."""
    working_output_dir = Path(__file__).parent.joinpath("output").resolve()
    working_output_dir.mkdir(exist_ok=True)
    src_control_output_path = Path("tests/config/hardware-layout.json").resolve()
    src_path = src.resolve()
    db = make_tst_layout(src_path)
    if write:
        db.write(src_control_output_path)
    working_path = working_output_dir.joinpath(f"{tag}.generated.json")
    db.write(working_path)
    show_layout.main(["-l", str(working_path)])
    print(".")

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
