# ruff: noqa: ANN401
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

from gwsproto.enums import MarketTypeName
from pydantic import BeforeValidator, Field

UTC_2000_01_01_TIMESTAMP = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp()
UTC_3000_01_01_TIMESTAMP = datetime(3000, 1, 1, tzinfo=timezone.utc).timestamp()


UTC_ISO_8601_SECONDS_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

UTC_ISO_8601_MILLIS_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"
)

SPACEHEAT_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
)

HANDLE_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*$"
)


def is_utc_iso8601_seconds(v: str) -> str:
    """
    utc.iso8601.seconds format:
    UTC timestamp in ISO 8601 format with second precision (no fractional seconds)
    and a 'Z' suffix.
    Example: 2025-02-26T00:00:00Z
    """
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: utc.iso8601.seconds must be a string.")

    if not UTC_ISO_8601_SECONDS_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails utc.iso8601.seconds format.")

    return v


def is_utc_iso8601_millis(v: str) -> str:
    """
    utc.iso8601.millis format:
    UTC timestamp in ISO 8601 format with exactly three digits of fractional
    seconds and a 'Z' suffix.
    Example: 2025-02-26T00:00:00.000Z
    """
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: utc.iso8601.millis must be a string.")

    if not UTC_ISO_8601_MILLIS_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails utc.iso8601.millis format.")

    return v


def check_is_log_style_date_with_millis(v: str) -> None:
    """Checks LogStyleDateWithMillis format

    LogStyleDateWithMillis format:  YYYY-MM-DDTHH:mm:ss.SSS

    Args:
        v (str): the candidate

    Raises:
        ValueError: if v is not LogStyleDateWithMillis format.
        In particular the milliseconds must have exactly 3 digits.
    """
    correct_millisecond_part_length = 3
    try:
        datetime.fromisoformat(v)
    except ValueError as e:
        raise ValueError(f"{v} is not in LogStyleDateWithMillis format") from e
    # The python fromisoformat allows for either 3 digits (milli) or 6 (micro)
    # after the final period. Make sure its 3
    milliseconds_part = v.split(".")[1]
    if len(milliseconds_part) != correct_millisecond_part_length:
        raise ValueError(
            f"{v} is not in LogStyleDateWithMillis format."
            " Milliseconds must have exactly 3 digits"
        )


def is_handle_name(v: str) -> str:
    """
    HandleName format:
    Dot-separated hierarchical identifier composed of lowercase
    alphanumeric segments with optional internal hyphen-separated words.

    Rules:
      - Each segment must start with a lowercase letter
      - Hyphens may appear only between alphanumeric characters
      - No trailing or leading hyphens in any segment
      - No empty segments
      - Entire string must be lowercase
    """
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: HandleName must be a string.")

    if not HANDLE_NAME_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails HandleName format.")

    return v


def is_hex_char(v: str) -> str:
    """Checks HexChar format

    HexChar format: single-char string in '0123456789abcdefABCDEF'

    Args:
        v (str): the candidate

    Raises:
        ValueError: if v is not HexChar format
    """
    if not isinstance(v, str):
        raise ValueError(f"<{v}> must be string. Got type <{type(v)}")  # noqa: TRY004
    if len(v) != 1:
        raise ValueError(f"<{v}> must be a hex char (exactly one character)")
    if v not in "0123456789abcdefABCDEF":
        raise ValueError(f"<{v}> must be one of '0123456789abcdefABCDEF'")
    return v


def is_int(v: int) -> int:
    if not isinstance(v, int):
        raise TypeError("Not an integer!")
    return v


def is_hh_mm(candidate: str) -> str:
    """Wall-clock time of day at minute resolution: 24-hour zero-padded
    "HH:MM" ("00:00" through "23:59"). Timezone-free.

    Raises:
        ValueError: if candidate is not of hh.mm format (e.g. "07:00")
    """
    if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", candidate):
        raise ValueError(f"<{candidate}>: Fails hh.mm format.")
    return candidate


def is_left_right_dot(candidate: str) -> str:
    """Lowercase AlphanumericStrings separated by dots (i.e. periods), with most
    significant word to the left.  I.e. `d1.ne` is the child of `d1`.
    Checking the format cannot verify the significance of words. All
    words must be alphanumeric. Most significant word must start with
    an alphabet charecter


    Raises:
        ValueError: if candidate is not of lrd format (e.g. d1.iso.me.apple)
    """
    try:
        x: list[str] = candidate.split(".")
    except Exception as e:
        raise ValueError("Failed to seperate into words with split'.'") from e
    first_word = x[0]
    first_char = first_word[0]
    if not first_char.isalpha():
        raise ValueError(
            f"Most significant word must start with alphabet char. Got '{first_word}'"
        )
    for word in x:
        if not word.isalnum():
            raise ValueError(
                f"words seperated by dots must be alphanumeric. Got '{word}'"
            )
    if not candidate.islower():
        raise ValueError(f"alias must be lowercase. Got '{candidate}'")
    return candidate


MAC_REGEX = re.compile("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$")


def has_mac_address_format(mac_str: str) -> bool:
    return bool(MAC_REGEX.match(mac_str.lower()))


def is_spaceheat_name(v: str) -> str:
    """
    Validate the SpaceheatName format.

    Rules:
      - Must be a string
      - Single segment (no dots)
      - Must start with a lowercase alphabetic character
      - May contain lowercase alphanumeric characters
      - Hyphens allowed only between alphanumeric characters
      - No leading or trailing hyphens
      - No consecutive hyphens
      - Entire string must be lowercase
      - Maximum length 64 characters
    """
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: SpaceheatName must be a string.")

    if len(v) > 64:
        raise ValueError(f"<{v}>: SpaceheatName exceeds maximum length of 64.")

    if not SPACEHEAT_NAME_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails SpaceheatName format.")

    return v


def is_uuid4_str(v: str) -> str:
    v = str(v)
    try:
        u = uuid.UUID(v)
    except Exception as e:
        raise ValueError(f"Invalid UUID4: <{v}  <{e}>") from e
    if u.version != 4:
        raise ValueError(f"{v} is valid uid, but of version {u.version}, not 4")
    return str(u)


def is_world_instance_name_format(candidate: str) -> bool:
    try:
        words = candidate.split("__")
    except:  # noqa
        return False
    if len(words) != 2:
        return False
    try:
        int(words[1])
    except:  # noqa
        return False
    try:
        root_g_node_alias_words = words[0].split(".")
    except:  # noqa
        return False
    return not len(root_g_node_alias_words) > 1


def check_is_ads1115_i2c_address(v: int) -> None:
    """
    Ads1115I2cAddress: v [0x48, 0x49, 0x4a, 0x4b].

    One of the 4 allowable I2C addresses for Texas Instrument Ads1115 chips.

    Raises:
        ValueError: if not Ads1115I2cAddress format
    """
    if v not in [0x48, 0x49, 0x4A, 0x4B]:
        raise ValueError(f"Not Ads1115I2cAddress: <{hex(v)}>")


def check_is_near5(v: str | float) -> None:
    """
    4.5  <= v  <= 5.5
    """
    v = float(v)
    min_pi_voltage = 4.5
    max_pi_voltage = 5.5
    if v < min_pi_voltage or v > max_pi_voltage:
        raise ValueError(f"<{v}> is not between 4.5 and 5.5, not Near5")


def is_bit(candidate: int) -> int:
    if candidate not in (0, 1):
        raise ValueError(f"Candidate must be 0 or 1, Got {candidate}")
    return candidate


def is_non_negative_int(candidate: int) -> int:
    # Non-coercive, mirroring the Sema `non.negative.int` format: the value must
    # already be an int (not a bool, float, or string) and >= 0.
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise ValueError(f"Must be an integer, got {candidate!r}")
    if candidate < 0:
        raise ValueError(f"Must be non-negative, got {candidate}")
    return candidate


def is_pascal_case(candidate: str) -> str:
    # Mirrors the Sema `pascal.case` format: a non-empty PascalCase identifier of
    # ASCII alphanumerics whose first character is an uppercase letter.
    if not isinstance(candidate, str):
        raise ValueError(f"PascalCase must be a string, got {candidate!r}")
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", candidate):
        raise ValueError(f"<{candidate}>: must be PascalCase (^[A-Z][A-Za-z0-9]*$)")
    return candidate


def is_market_name(v: str) -> str:
    try:
        x = v.split(".")
    except AttributeError as e:
        raise ValueError(f"{v} failed to split on '.'") from e
    if len(x) < 3:
        raise ValueError("MarketNames need at least 3 words")
    if x[0] not in {"e", "r", "d"}:
        raise ValueError(
            f"{v} first word must be e,r or d (energy, regulation, distribution)"
        )
    if x[1] not in MarketTypeName.values():
        raise ValueError(f"{v} not recognized MarketType")
    g_node_alias = ".".join(x[2:])
    is_left_right_dot(g_node_alias)
    return v


def is_market_slot_name(v: str) -> str:
    r"""Checks market.slot.name format against the sema contract.

    Sema pattern (maker-agnostic): a leading market kind (e/r/d), a product
    token, the MarketMaker GNodeAlias words, and a 10-digit slot-start epoch:
        ^[erd]\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.[a-z][a-z0-9]*(?:\.[a-z0-9]+)*\.[0-9]{10}$
    Whether the product token names a real product, and whether the slot start
    aligns to that product's duration, are the receiving market maker's concern
    — not this format (sema formats/market.slot.name).
    """
    if not isinstance(v, str):
        raise ValueError(f"<{v}> must be a string. Got type <{type(v)}>")  # noqa: TRY004
    if not re.match(
        r"^[erd]\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.[a-z][a-z0-9]*(?:\.[a-z0-9]+)*\.[0-9]{10}$",
        v,
    ):
        raise ValueError(f"<{v}> is not market.slot.name format")
    return v


Bit = Annotated[int, BeforeValidator(is_bit)]
HandleName = Annotated[str, BeforeValidator(is_handle_name)]
HexChar = Annotated[str, BeforeValidator(is_hex_char)]
HhMm = Annotated[str, BeforeValidator(is_hh_mm)]
LeftRightDotStr = Annotated[str, BeforeValidator(is_left_right_dot)]
MarketName = Annotated[str, BeforeValidator(is_market_name)]
MarketSlotName = Annotated[str, BeforeValidator(is_market_slot_name)]
NonNegativeInt = Annotated[int, BeforeValidator(is_non_negative_int)]
PascalCase = Annotated[str, BeforeValidator(is_pascal_case)]
SpaceheatName = Annotated[str, BeforeValidator(is_spaceheat_name)]
UUID4Str = Annotated[str, BeforeValidator(is_uuid4_str)]
UTCSeconds = Annotated[
    int, Field(ge=UTC_2000_01_01_TIMESTAMP, le=UTC_3000_01_01_TIMESTAMP)
]
UTCMilliseconds = Annotated[
    int, Field(ge=UTC_2000_01_01_TIMESTAMP * 1000, le=UTC_3000_01_01_TIMESTAMP * 1000)
]
UtcIso8601Seconds = Annotated[str, BeforeValidator(is_utc_iso8601_seconds)]
UtcIso8601Millis = Annotated[str, BeforeValidator(is_utc_iso8601_millis)]
