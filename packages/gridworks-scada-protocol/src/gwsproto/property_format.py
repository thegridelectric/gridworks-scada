# ruff: noqa: ANN401
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

from gw.enums import MarketTypeName
from pydantic import BeforeValidator, Field

UTC_2000_01_01_TIMESTAMP = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp()
UTC_3000_01_01_TIMESTAMP = datetime(3000, 1, 1, tzinfo=timezone.utc).timestamp()


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
    HandleName format: words separated by periods, where the worlds are lowercase
    alphanumeric plus hyphens
    """
    try:
        x = v.split(".")
    except Exception as e:
        raise ValueError(f"Failed to seperate <{v}> into words with split'.'") from e
    first_word = x[0]
    first_char = first_word[0]
    if not first_char.isalpha():
        raise ValueError(
            f"Most significant word of <{v}> must start wif64th alphabet char."
        )
    for word in x:
        for char in word:
            if not (char.isalnum() or char == "-"):
                raise ValueError(
                    f"words of <{v}> split by by '.' must be alphanumeric or hyphen."
                )
    if not v.islower():
        raise ValueError(f" <{v}> must be lowercase.")
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
    if len(v) > 1:
        raise ValueError(f"<{v}> must be a hex char, but not of len 1")
    if v not in "0123456789abcdefABCDEF":
        raise ValueError(f"<{v}> must be one of '0123456789abcdefABCDEF'")
    return v


def is_int(v: int) -> int:
    if not isinstance(v, int):
        raise TypeError("Not an integer!")
    return v


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
    SpaceheatName format: Lowercase alphanumeric words separated by hypens
    """
    try:
        x = v.split("-")
    except Exception as e:
        raise ValueError(
            f"<{v}>: Fails SpaceheatName format! Failed to seperate into words with split'-'"
        ) from e
    first_word = x[0]
    first_char = first_word[0]
    if not first_char.isalpha():
        raise ValueError(
            f"<{v}>: Fails SpaceheatName format! Most significant word  must start with alphabet char."
        )
    for word in x:
        if not word.isalnum():
            raise ValueError(
                f"<{v}>: Fails SpaceheatName format! words of split by by '-' must be alphanumeric."
            )
    if not v.islower():
        raise ValueError(
            f"<{v}>: Fails SpaceheatName format! All characters of  must be lowercase."
        )
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


MarketMinutes: dict[MarketTypeName, int] = {
    MarketTypeName.da60: 60,
    MarketTypeName.rt15gate5: 15,
    MarketTypeName.rt30gate5: 30,
    MarketTypeName.rt5gate5: 5,
    MarketTypeName.rt60gate30: 60,
    MarketTypeName.rt60gate30b: 60,
    MarketTypeName.rt60gate5: 60,
}


def is_market_slot_name(v: str) -> str:
    """
    MaketSlotNameLrdFormat: the format of a MarketSlotName.
      - First word must be e, r or d (energy, regulation, distribution)
      - The second word must be a MarketTypeName
      - The last word (unix time of market slot start) must
      be a 10-digit integer divisible by 300 (i.e. all MarketSlots
      start at the top of 5 minutes)
      - More strictly, the last word must be the start of a
      MarketSlot for that MarketType (i.e. divisible by 3600
      for hourly markets)
      - The middle words have LeftRightDot format (GNodeAlias
      of the MarketMaker)
    Example: e.rt60gate5.d1.isone.ver.keene.1673539200

    """
    try:
        x = v.split(".")
    except AttributeError:
        raise ValueError(f"{v} failed to split on '.'")
    slot_start_str = x[-1]
    if len(slot_start_str) != 10:
        raise ValueError(f"slot start {slot_start_str} not of length 10")
    try:
        slot_start = int(slot_start_str)
    except ValueError:
        raise ValueError(f"slot start {slot_start_str} not an int")
    is_market_name(".".join(x[:-1]))
    market_type_name = MarketTypeName(x[1])
    market_duration_minutes = MarketMinutes[market_type_name]
    if not slot_start % (market_duration_minutes * 60) == 0:
        raise ValueError(
            f"market_slot_start_s mod {market_duration_minutes * 60} must be 0"
        )
    return v


Bit = Annotated[int, BeforeValidator(is_bit)]
HandleName = Annotated[str, BeforeValidator(is_handle_name)]
HexChar = Annotated[str, BeforeValidator(is_hex_char)]
LeftRightDotStr = Annotated[str, BeforeValidator(is_left_right_dot)]
MarketName = Annotated[str, BeforeValidator(is_market_name)]
MarketSlotName = Annotated[str, BeforeValidator(is_market_slot_name)]
SpaceheatName = Annotated[str, BeforeValidator(is_spaceheat_name)]
UUID4Str = Annotated[str, BeforeValidator(is_uuid4_str)]
UTCSeconds = Annotated[
    int, Field(ge=UTC_2000_01_01_TIMESTAMP, le=UTC_3000_01_01_TIMESTAMP)
]
UTCMilliseconds = Annotated[
    int, Field(ge=UTC_2000_01_01_TIMESTAMP * 1000, le=UTC_3000_01_01_TIMESTAMP * 1000)
]
