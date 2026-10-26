import argparse
import time
from pathlib import Path
import socket

import xdg
from pyModbusTCP.client import ModbusClient
import rich.traceback
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.table import Column


from drivers.power_meter.egauge.registers import EGaugeRegister
from drivers.power_meter.egauge.registers import EGaugeRegisters
from drivers.power_meter.egauge.registers import read_register
from drivers.power_meter.egauge.registers import RegisterType

rich.traceback.install(show_locals=True)


def generate_table(registers: list[EGaugeRegister], raw_values: list) -> Table:
    table = Table(
        Column("Offset", header_style="cyan", style="cyan"),
        Column("Name", header_style="green", style="green"),
        Column("Description", header_style="green", style="green"),
        Column("Value", header_style="bold cyan", style="bold cyan", justify="right"),
        Column("Unit", header_style="orchid1", style="orchid1"),
    )
    for register, raw_value in zip(registers, raw_values):
        if register.Type == RegisterType.f32:
            value = f"{raw_value / register.Denominator: 10.4f}"
        elif register.Type in (RegisterType.u32, RegisterType.s64):
            value = f"{int(raw_value / int(register.Denominator))}"
        elif isinstance(register, bytes):
            value = raw_value.decode("utf-8").rstrip('\x00')
        else:
            value = str(raw_value)
        table.add_row(
            str(register.offset),
            register.Name,
            register.Description,
            value,
            register.Unit,
        )
    return table


def watch():
    parser = argparse.ArgumentParser()
    parser.add_argument("-H", "--host", type=str, default="localhost", help="Host (default: localhost)")
    parser.add_argument("-p", "--port", type=int, default=502, help="TCP port (default: 502)")
    parser.add_argument(
        "--register-csv",
        default=Path(f"{xdg.xdg_config_home()}/gridworks/scada/egauge-modbus-map.csv")
    )
    parser.add_argument(
        "--register-table-svg",
        default=Path(f"{xdg.xdg_state_home()}/gridworks/scada/eguage-register-table.svg")
    )
    parser.add_argument(
        "--register-values-svg",
        default=Path(f"{xdg.xdg_state_home()}/gridworks/scada/eguage-register-values.svg")
    )
    args = parser.parse_args()
    register_csv_path = Path(args.register_csv)
    console = Console(record=True)
    if not register_csv_path.exists():
        console.print(
            f" [bold]:thumbs_down: register csv path {register_csv_path} does not exist.\n\n[/]"
            f" Export it from the Eguage website for this device under 'settings/Modbus Server/Export Modbus Map'"
        )
        return
    registers = EGaugeRegisters.from_csv(register_csv_path)
    console.print(registers.get_table())
    register_values_path = Path(args.register_values_svg)
    if not register_values_path.parent.exists():
        register_values_path.parent.mkdir(parents=True, exist_ok=True)
    register_table_path = Path(args.register_table_svg)
    if not register_table_path.parent.exists():
        register_table_path.parent.mkdir(parents=True, exist_ok=True)
    console.save_svg(str(register_table_path), clear=True)
    excluded = {30002, 30004, 30006, 30008, 30010}
    registers = [
        register
        for register in registers.registers()
        if (
            not register.Address in excluded and
            not register.Deprecated and
            not register.Name.startswith("Virtual")
        )
    ]
    unresolved_host = args.host
    args.host = socket.gethostbyname(args.host)
    console.print(f"Modbus host: {unresolved_host} -> {args.host}")
    c = ModbusClient(host=args.host, port=args.port, unit_id=1, timeout=5.0, auto_open=True)
    try:
        c.open()
        if c.is_open:
            with Live(
                generate_table(
                    registers,
                    [read_register(c, register)[2] for register in registers]
                ),
                console=console
            ) as live:
                while c.is_open:
                    time.sleep(1)
                    table = generate_table(
                        registers,
                        [read_register(c, register)[2] for register in registers]
                    )
                    live.update(table)
                    with register_values_path.open("w") as f:
                        save_console = Console(record=True, file=f)
                        save_console.print(table)
                        save_console.save_svg(str(register_values_path), clear=True)
                    if not c.is_open:
                        time.sleep(1)
                        c.open()
                        if not c.is_open:
                            raise ValueError("ERROR. Connection to Modbus server lost")

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    watch()
