import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BeforeValidator, Field, StrictFloat, StrictInt


# --- patterns ---
FIRMWARE_COMMIT_PATTERN = re.compile(r"^([0-9a-f]{40}(-dirty)?|unstamped)$")

GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}(-dirty)?$")

HANDLE_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*$"
)

HH_MM_PATTERN = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

IANA_TIMEZONE_STR_PATTERN = re.compile(r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$")

LEFT_RIGHT_DOT_PATTERN = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9]+)*$")

MAC_ADDRESS_PATTERN = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")

MARKET_SLOT_NAME_PATTERN = re.compile(
    r"^[erd]\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.[a-z][a-z0-9]*(?:\.[a-z0-9]+)*\.[0-9]{10}$"
)

PASCAL_CASE_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")

POSITIVE_INT_AS_STR_PATTERN = re.compile(r"^[1-9][0-9]*$")

SPACEHEAT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

UTC_ISO8601_SECONDS_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

UUID4_STR_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


# --- methods ---
def is_decimal_digit(v: int) -> int:
    if not isinstance(v, int):
        raise TypeError("Not an int!")
    if v < 0 or v > 9:
        raise ValueError(f"{v} must be a single decimal digit, 0 through 9")
    return v


def is_firmware_commit(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: firmware.commit must be a string.")

    if not FIRMWARE_COMMIT_PATTERN.fullmatch(v):
        raise ValueError(
            f"<{v}>: Fails firmware.commit format (a 40-character lowercase "
            "git hash, optionally suffixed -dirty, or the literal unstamped)."
        )

    return v


def is_git_commit(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: git.commit must be a string.")

    if not GIT_COMMIT_PATTERN.fullmatch(v):
        raise ValueError(
            f"<{v}>: Fails git.commit format (a 40-character lowercase "
            "git hash, optionally suffixed -dirty)."
        )

    return v


def is_handle_name(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: HandleName must be a string.")

    if not HANDLE_NAME_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails HandleName format.")

    return v


def is_hh_mm(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: hh.mm must be a string.")

    if not HH_MM_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails hh.mm format.")

    return v


def is_iana_timezone_str(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: iana.timezone.str must be a string.")

    if not IANA_TIMEZONE_STR_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails iana.timezone.str format.")

    return v


def is_left_right_dot(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: LeftRightDot must be a string.")

    if not LEFT_RIGHT_DOT_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails LeftRightDot format.")

    return v


def is_mac_address(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: mac.address must be a string.")

    if not MAC_ADDRESS_PATTERN.fullmatch(v):
        raise ValueError(
            f"<{v}>: Fails mac.address format (six lowercase hex octet pairs, colon-separated)."
        )

    return v


def is_market_slot_name(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: market.slot.name must be a string.")

    if not MARKET_SLOT_NAME_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails market.slot.name format.")

    slot_start = int(v.rsplit(".", 1)[1])
    if slot_start % 300 != 0:
        raise ValueError(
            f"<{v}>: market.slot.name slot start {slot_start} must be divisible "
            "by 300 (every market slot starts on a 5-minute grid)."
        )

    return v


def is_non_negative_int(v: int) -> int:
    if not isinstance(v, int):
        raise TypeError("Not an int!")
    if v < 0:
        raise ValueError(f"{v} must be non-negative")
    return v


def is_pascal_case(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: PascalCase must be a string.")

    if not PASCAL_CASE_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails PascalCase format.")

    return v


def is_positive_int(v: int) -> int:
    if not isinstance(v, int) or isinstance(v, bool):
        raise TypeError("Not an int!")
    if v <= 0:
        raise ValueError(f"{v} must be positive")
    return v


def is_positive_int_as_str(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: positive.int.as.str must be a string.")
    if not POSITIVE_INT_AS_STR_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails positive.int.as.str format.")
    return v


def is_spaceheat_name(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: SpaceheatName must be a string.")

    if len(v) > 64:
        raise ValueError(f"<{v}>: SpaceheatName exceeds maximum length of 64.")

    if not SPACEHEAT_NAME_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails SpaceheatName format.")

    return v


def is_utc_iso8601_seconds(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: utc.iso8601.seconds must be a string.")

    if not UTC_ISO8601_SECONDS_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails utc.iso8601.seconds format.")

    return v


def is_utc_milliseconds(v: int) -> int:
    if not isinstance(v, int):
        raise TypeError("Not an int!")
    start_date = datetime(2000, 1, 1, tzinfo=UTC)
    end_date = datetime(3000, 1, 1, tzinfo=UTC)

    start_timestamp_ms = int(start_date.timestamp() * 1000)
    end_timestamp_ms = int(end_date.timestamp() * 1000)

    if v < start_timestamp_ms:
        raise ValueError(f"{v} must be after Jan 1 2000")
    if v > end_timestamp_ms:
        raise ValueError(f"{v} must be before Jan 1 3000")
    return v


def is_utc_seconds(v: int) -> int:
    if not isinstance(v, int):
        raise ValueError("Not an int!")
    start_date = datetime(2000, 1, 1, tzinfo=UTC)
    end_date = datetime(3000, 1, 1, tzinfo=UTC)

    start_timestamp = int(start_date.timestamp())
    end_timestamp = int(end_date.timestamp())

    if v < start_timestamp:
        raise ValueError(f"{v}: Fails UTCSeconds format! Must be after Jan 1 2000")
    if v > end_timestamp:
        raise ValueError(f"{v}: Fails UTCSeconds format! Must be before Jan 1 3000")
    return v


def is_uuid4_str(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"<{v}>: uuid4.str must be a string.")

    if not UUID4_STR_PATTERN.fullmatch(v):
        raise ValueError(f"<{v}>: Fails uuid4.str format.")

    try:
        u = uuid.UUID(v)
    except Exception as e:
        raise ValueError(f"Invalid UUID4: {v}  <{e}>") from e
    if u.version != 4:
        raise ValueError(
            f"{v} is valid uid, but of version {u.version}. Fails UuidCanonicalTextual"
        )
    return str(u)


# --- annotated types ---
DecimalDigit = Annotated[
    StrictInt,
    Field(ge=0, le=9),
]

FirmwareCommit = Annotated[
    str,
    BeforeValidator(is_firmware_commit),
]

GitCommit = Annotated[
    str,
    BeforeValidator(is_git_commit),
]

HandleName = Annotated[
    str,
    BeforeValidator(is_handle_name),
]

HhMm = Annotated[
    str,
    BeforeValidator(is_hh_mm),
]

IanaTimezoneStr = Annotated[
    str,
    BeforeValidator(is_iana_timezone_str),
]

LeftRightDot = Annotated[
    str,
    BeforeValidator(is_left_right_dot),
]

MacAddress = Annotated[
    str,
    BeforeValidator(is_mac_address),
]

MarketSlotName = Annotated[
    str,
    BeforeValidator(is_market_slot_name),
]

NonEmptyString = Annotated[
    str,
    Field(min_length=1),
]

NonNegativeInt = Annotated[
    StrictInt,
    Field(ge=0),
]

PascalCase = Annotated[
    str,
    BeforeValidator(is_pascal_case),
]

PositiveFloat = Annotated[
    StrictFloat,
    Field(gt=0),
]

PositiveInt = Annotated[
    int,
    BeforeValidator(is_positive_int),
]

PositiveIntAsStr = Annotated[
    str,
    BeforeValidator(is_positive_int_as_str),
]

SpaceheatName = Annotated[
    str,
    BeforeValidator(is_spaceheat_name),
]

UtcIso8601Seconds = Annotated[
    str,
    BeforeValidator(is_utc_iso8601_seconds),
]

UTCMilliseconds = Annotated[
    int,
    BeforeValidator(is_utc_milliseconds),
]

UTCSeconds = Annotated[
    int,
    BeforeValidator(is_utc_seconds),
]

UUID4Str = Annotated[
    str,
    BeforeValidator(is_uuid4_str),
]


# --- helpers ---
class UtcIso8601SecondsFormat:
    @staticmethod
    def from_datetime(dt: datetime) -> UtcIso8601Seconds:
        if not isinstance(dt, datetime):
            raise TypeError(f"{dt} must be a datetime")

        if dt.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")

        dt_utc = dt.astimezone(UTC)
        dt_utc = dt_utc.replace(microsecond=0)
        s = dt_utc.isoformat().replace("+00:00", "Z")

        return is_utc_iso8601_seconds(s)
