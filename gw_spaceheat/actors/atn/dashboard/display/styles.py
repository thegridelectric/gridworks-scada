from typing import Callable
from typing import Optional

from rich.style import Style
from rich.text import Text

misc_style = Style(bold=True, color="#008000")
cold_style = Style(bold=True, color="cyan1")
hot_style = Style(bold=True, color="dark_orange")
none_text = Text("NA", style=misc_style)

def temperature_color(
    degrees: float,
    graded_min: int = 32,
    graded_max: int = 100,
    cyan_ceiling: int = 40,
    cyan_graded_degrees: int = 8,
) -> str:
    num_graded_degrees = graded_max - graded_min
    red_graded_degrees = max(min(degrees - graded_min, num_graded_degrees), 0)
    red_fraction = red_graded_degrees / num_graded_degrees
    red = int(red_fraction * 255)
    blue = int((1 - red_fraction) * 255)
    if degrees <= cyan_ceiling:
        green_graded_degrees = min(abs(cyan_ceiling - degrees), cyan_graded_degrees)
        green_fraction =  green_graded_degrees / cyan_graded_degrees
        green = int(green_fraction * 255)
    else:
        green = 0
    return f"#{red:02X}{green:02X}{blue:02X}"

def fahrenheit_color(fahrenheit: float) -> str:
    return temperature_color(
        fahrenheit,
        graded_min=32,
        graded_max=100,
        cyan_ceiling=40,
        cyan_graded_degrees=8,
    )

def fahrenheit_style(fahrenheit: float) -> Style:
    return Style.parse(fahrenheit_color(fahrenheit))

def celcius_color(celcius: float) -> str:
    return temperature_color(
        celcius,
        graded_min=0,
        graded_max=100,
        cyan_ceiling=6,
        cyan_graded_degrees=6,
    )

def celcius_style(celcius: float) -> Style:
    return Style.parse(celcius_color(celcius))

def tank_color(fahrenheit: float) -> str:
    return temperature_color(
        fahrenheit,
        graded_min=32,
        graded_max=210,
        cyan_ceiling=32,
        cyan_graded_degrees=8,
    )

def tank_style(fahrenheit: float) -> Style:
    return Style.parse(tank_color(fahrenheit))

def temperature_text(
    temperature: Optional[float],
    style_calculator: Callable[[float | int], str | Style] | str | Style = fahrenheit_color,
    *,
    unit_str: str = "F",
    number_format_str: str = "{temperature:5.1f}",
) -> Text:
    if isinstance(style_calculator, (str, Style)):
        style = style_calculator
    else:
        style = style_calculator(temperature)
    if temperature is None:
        s = "  ---  "
    else:
        degree_str = number_format_str.format(temperature=temperature)
        s = f"{degree_str}°{unit_str}"
    return Text(s, style=style)

def temperature_markup(
    temperature: Optional[float],
    style_calculator: Callable[[float | int], str | Style] | str | Style = fahrenheit_color,
    *,
    unit_str: str = "F",
    number_format_str: str = "{temperature:5.1f}",
) -> str:
    return temperature_text(
        temperature=temperature,
        style_calculator=style_calculator,
        unit_str=unit_str,
        number_format_str=number_format_str,
    ).markup

def tank_temperature_text(temperature: float) -> Text:
    return temperature_text(temperature=temperature, style_calculator=tank_style)

def tank_temperature_markup(temperature: float) -> str:
    return tank_temperature_text(temperature=temperature).markup

