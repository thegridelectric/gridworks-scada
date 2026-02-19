import argparse
import sys
from pathlib import Path
from typing import Optional
from typing import Sequence

import dotenv
from gwsproto.data_classes.components.hubitat_component import HubitatComponent
from gwsproto.data_classes.components.hubitat_poller_component import HubitatPollerComponent
from rich import print
from rich.table import Table
from rich.text import Text

from actors.config import ScadaSettings
from command_line_utils import get_requested_names
from gwsproto.errors import DcError
from gwsproto.data_classes.hardware_layout import LoadError
from gwsproto.data_classes.house_0_layout import House0Layout

from gwsproto.enums import ActorClass

from scada_app import ScadaApp


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-e",
        "--env-file",
        default=".env",
        help=(
            "Name of .env file to locate with dotenv.find_dotenv(). Defaults to '.env'. "
            "Pass empty string in quotation marks to suppress use of .env file."
        ),
    )
    parser.add_argument(
        "-l",
        "--layout-file",
        default=None,
        help=(
            "Name of layout file (e.g. hardware-layout.json or apple for apple.json). "
            "If path is relative it will be relative to settings.paths.config_dir. "
            "If path has no extension, .json will be assumed. "
            "If not specified default settings.paths.hardware_layout will be used."
        ),
    )
    parser.add_argument(
        "-n",
        "--nodes",
        default=None,
        nargs="*",
        help="ShNode names to load.",
    )
    parser.add_argument(
        "-r",
        "--raise-errors",
        action="store_true",
        help="Raise any errors immediately to see full call stack."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print additional information"
    )
    parser.add_argument(
        "-t",
        "--table-only",
        action="store_true",
        help="Print only the table"
    )

    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def print_component_dicts(layout: House0Layout):
    print("All Components:")
    print({
        component.gt.ComponentId: component.gt.DisplayName
        for component in layout.components.values()
    })
    print("All Cacs:")
    print({
        cac.ComponentAttributeClassId: cac.DisplayName
        for cac in layout.cacs.values()
    })
    print("Nodes:")
    print(layout.nodes)
    print("Raw nodes:")
    print([n["Name"] for n in layout.layout["ShNodes"]])
    print("Node Component ids:")
    print({
        node.Name: node.component_id for node in layout.nodes.values()
    })
    print("Node Components")
    print({
        node.Name: layout.component(node.Name)
        for node in layout.nodes.values()
    })
    print("Node Cacs:")
    print({
        node.Name: layout.cac(node.Name)
        for node in layout.nodes.values()
    })
    # unused components
    unused_components = dict(layout.components)
    for node in layout.nodes.values():
        unused_components.pop(node.component_id, None)
    print(f"Unused Components: {len(unused_components)}")
    if unused_components:
        print(unused_components)
    # unused cacs
    unused_cacs = dict(layout.cacs)
    for component in layout.components.values():
        unused_cacs.pop(component.gt.ComponentAttributeClassId, None)
    print(f"Unused Cacs: {len(unused_cacs)}")
    if unused_cacs:
        print(unused_cacs)
    # dangling components
    dangling_component_nodes = set()
    for node in layout.nodes.values():
        if node.component_id and node.component_id not in layout.components:
            dangling_component_nodes.add(node.Name)
    print(f"Nodes with component_id but no component: {len(dangling_component_nodes)}")
    if dangling_component_nodes:
        print(sorted(dangling_component_nodes))
    # dangling cacs
    dangling_cac_components = set()
    for component in layout.components.values():
        if component.gt.ComponentAttributeClassId and component.gt.ComponentAttributeClassId not in layout.cacs:
            dangling_cac_components.add(component.gt.DisplayName)
    print(f"Components with cac_id but no cac: {len(dangling_cac_components)}")
    if dangling_cac_components:
        print(sorted(dangling_cac_components))


def print_layout_members(
    layout: House0Layout,
    errors: Optional[list[LoadError]] = None,
) -> None:
    if errors is None:
        errors = []

    print("Layout identifier attributes")
    for attr in [
        "ltn_g_node_alias",
        "ltn_g_node_instance_id",
        "ltn_g_node_id",
        "terminal_asset_g_node_alias",
        "terminal_asset_g_node_id",
        "scada_g_node_alias",
        "scada_g_node_id",
    ]:
        try:
            print(f"  {attr}: <{getattr(layout, attr)}>")
        except Exception as e:
            errors.append(LoadError(attr, {}, e))
    print("Layout named items")

    try:
        attr = "power_meter_component"
        item = getattr(layout, attr)
        display = None if item is None else item.gt.DisplayName
        print(f"  {attr}: <{display}>")
    except Exception as e:
        errors.append(LoadError(attr, {}, e))

    try:
        attr = "power_meter_cac"
        item = getattr(layout, attr)
        display = None if item is None else item.DisplayName
        print(f"  {attr}: <{display}>")
    except Exception as e:
        errors.append(LoadError(attr, {}, e))


    for attr in [
        "power_meter_node",
    ]:
        try:
            item = getattr(layout, attr)
            display = None if item is None else item.display_name
            print(f"  {attr}: <{display}>")
        except Exception as e:
            errors.append(LoadError(attr, {}, e))


    print("Named layout collections:")
    for attr in [
        "all_nodes_in_agg_power_metering",
    ]:
        print(f"  {attr}:")
        try:
            for entry in getattr(layout, attr):
                print(f"    <{entry.Name}>")
        except Exception as e:
            errors.append(LoadError(attr, {}, e))

def print_layout_urls(layout: House0Layout) -> None:
    url_dicts = {
        component.gt.DisplayName: component.urls()
        for component in [
        component for component in layout.components.values()
        if isinstance(component, (HubitatComponent, HubitatPollerComponent))
    ]
    }
    if url_dicts:
        print("Component URLS:")
        for name, urls in url_dicts.items():
            print(f"  <{name}>:")
            for k, v in urls.items():
                print(f"    {k}: {str(v)}")

def print_web_server_info(
    settings: ScadaSettings,
) -> None:
    scada_app = try_scada_load(
        settings,
        raise_errors=False
    )
    if scada_app is None:
        print("Cannot print Web server configs and routes since Scada could not be loaded")
    else:
        web_configs = scada_app.get_web_server_configs()
        web_routes = scada_app.get_web_server_route_strings()
        print(f"Web server configs: {len(web_configs)}")
        if web_configs.keys() != web_routes.keys():
           print(
               "Keys for web configs and web routes do not match:\n"
               f"  configs: {web_configs.keys()}\n"
               f"  routes:  {web_routes.keys()}"
           )
        for k, v in web_configs.items():
            print(f"Server <{k}>: WebServerGt({v})")
            routes = web_routes.get(k, [])
            print(f"Routes: {len(routes)}")
            for route in routes:
                print(f"  {route}")

def print_channels(layout: House0Layout, *, raise_errors: bool = False) -> None:
    print()
    try:
        table = Table(
            title="Data channels",
            title_justify="left",
            title_style="bold blue",
        )
        table.add_column("Channel Name", header_style="bold green", style="green")
        table.add_column("About", header_style="bold dark_orange", style="dark_orange")
        table.add_column("Capturer", header_style="bold dark_orange", style="dark_orange")
        table.add_column("Telemetry", header_style="bold green1", style="green1")
        table.add_column("Power", header_style="bold red", style="red")

        for channel in layout.data_channels.values():
            table.add_row(
                Text(channel.Name),
                Text(channel.AboutNodeName),
                Text(channel.CapturedByNodeName),
                Text(channel.TelemetryName),
                Text("✔" if channel.InPowerMetering else ""),
            )
        print(table)
    except Exception as e: # noqa
        print(f"ERROR printing channels: <{e}> {type(e)}")
        print("Use '-r' to see full error stack.")
        if raise_errors:
            raise

def print_layout_table(layout: House0Layout):
    print()
    table = Table(
        title="Nodes, Components, Cacs, Actors",
        title_justify="left",
        title_style="bold blue",
    )
    table.add_column("Node", header_style="bold green", style="green")
    table.add_column("Component", header_style="bold dark_orange", style="dark_orange")
    table.add_column("Cac", header_style="bold dark_orange", style="dark_orange")
    table.add_column("Make/Model", header_style="bold dark_orange", style="dark_orange")
    table.add_column("Actor", header_style="bold green1", style="green1")
    none_text = Text("None", style="cyan")
    for node in layout.nodes.values():
        component = layout.component(node.Name)
        if component is None:
            if node.component_id:
                component_txt = Text("MISSING", style="red") + \
                    Text(f" Component {node.component_id[:8]}", style=none_text.style)
            else:
                component_txt = none_text
        else:
            component_txt = str(component.gt.DisplayName)
        cac = layout.cac(node.Name)
        if cac is None:
            make_model_text = none_text
            if component is not None and component.gt.ComponentAttributeClassId:
                cac_txt = Text("MISSING", style="red") + \
                    Text(f" Cac {component.gt.ComponentAttributeClassId[:8]}", style=none_text.style)
            else:
                cac_txt = none_text

        else:
            if cac.DisplayName:
                cac_txt = Text(cac.DisplayName, style=table.columns[2].style)
            else:
                cac_txt = Text("Cac id: ") + Text(cac.ComponentAttributeClassId, style="light_coral")
            if hasattr(cac, "MakeModel"):
                make_model_text = Text(str(cac.MakeModel), style=table.columns[3].style)
            else:
                make_model_text = none_text
        node = layout.node(node.Name)
        if node.actor_class and node.actor_class != ActorClass.NoActor:
            actor_text = Text(str(node.actor_class))
        else:
            actor_text = none_text
        table.add_row(node.Name, component_txt, cac_txt, make_model_text, actor_text)
    print(table)

def try_scada_load(settings: ScadaSettings, raise_errors: bool = False) -> Optional[ScadaApp]:
    settings = settings.model_copy(deep=True)
    settings.paths.mkdirs()
    scada_app = None
    try:
        scada_app = ScadaApp(
            app_settings=settings,
        )
        scada_app.instantiate()
    except (
            DcError,
            KeyError,
            ModuleNotFoundError,
            ValueError,
            FileNotFoundError,
            AttributeError,
            StopIteration,
    ) as e:
        print(f"ERROR loading Scada: <{e}> {type(e)}")
        print("Use '-r' to see full error stack.")
        if raise_errors:
            raise e
    return scada_app

def show_layout(
        layout: House0Layout,
        settings: ScadaSettings,
        raise_errors: bool = False,
        errors: Optional[list[LoadError]] = None,
        table_only: bool = False,
) -> ScadaApp:
    if errors is None:
        errors = []
    if not table_only:
        print_component_dicts(layout)
        print_layout_members(layout, errors)
        print_layout_urls(layout)
        print_web_server_info(settings)
        print_channels(layout, raise_errors=raise_errors)
    print_layout_table(layout)
    scada_app = try_scada_load(
        settings,
        raise_errors=raise_errors
    )
    return scada_app

def main(argv: Optional[Sequence[str]] = None) -> list[LoadError]:
    args = parse_args(argv)
    dotenv_file = dotenv.find_dotenv(args.env_file)
    print(f"Using .env file {dotenv_file}, exists: {Path(dotenv_file).exists()}")
    settings = ScadaSettings(_env_file=dotenv_file)
    if args.layout_file:
        layout_path = Path(args.layout_file)
        if Path(layout_path.name) == layout_path:
            layout_path = settings.paths.config_dir / layout_path
        if not layout_path.suffix:
            layout_path = layout_path.with_suffix(".json")
        settings.paths.hardware_layout = layout_path
    requested_names = get_requested_names(args)
    print(f"Using layout file: <{settings.paths.hardware_layout}>, exists: {settings.paths.hardware_layout.exists()}")
    errors = []
    layout = House0Layout.load(
        settings.paths.hardware_layout,
        included_node_names=requested_names,
        raise_errors=bool(args.raise_errors),
        errors=errors,
    )
    show_layout(
        layout,
        settings,
        raise_errors=args.raise_errors,
        errors=errors,
        table_only=args.table_only,
    )
    if errors:
        print(f"\nFound {len(errors)} ERRORS in layout:")
        for i, error in enumerate(errors):
            print(f"  {i+1:2d}: {error.type_name:30s}  <{error.src_dict.get('DisplayName', '')}>  <{error.exception}> ")
            if args.verbose:
                print(f"  {i+1:2d}:  element:\n{error.src_dict}\n")
        print(f"\nFound {len(errors)} ERRORS in layout.")
    return errors

if __name__ == "__main__":
    main()
