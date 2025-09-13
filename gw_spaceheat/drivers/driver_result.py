from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel

from gwsproto.enums import LogLevel

R = TypeVar("R", covariant=True)  # Result type

class Comment(BaseModel):
    """A comment about driver execution that can be converted into a Glitch"""
    level: LogLevel
    msg: str

T = TypeVar('T')

class DriverResult(Generic[R]):
    """A class which allows limited interface drivers any warnings that accumulated on the way to getting an actual result."""
    value: R
    warnings: list[Exception]

    def __init__(self, value: R, warnings: Optional[list[Exception]] = None):
        self.value = value
        if warnings is None:
            self.warnings = []
        else:
            self.warnings = warnings[:]


class DriverOutcome(Generic[T]):
    """
    Container for driver execution results. Rather than using exceptions for control flow,
    this provides structured communication about what happened during driver execution.

    The value can be None to indicate no result was obtained, but the execution wasn't 
    necessarily problematic - just nothing to report (e.g., during a backoff period).

    Comments provide structured feedback about the execution that can be converted to
    Glitches by higher level code.
    """
    value: Optional[T]
    comments: List[Comment]

    def __init__(
        self,
        value: Optional[T],
        comments: Optional[List[Comment]] = None
    ):
        self.value = value
        self.comments = comments or []

    def add_comment(self, level: LogLevel, msg: str) -> None:
        """Add a comment about the execution"""
        self.comments.append(Comment(level=level, msg=msg))

    def comments_to_details(self) -> str:
        """Joins all comment messages with newlines for use in Glitch Details"""
        return "\n".join(comment.msg for comment in self.comments)

    def get_highest_level(self) -> Optional[LogLevel]:
        """Returns the highest LogLevel among comments, or None if no comments"""
        if not self.comments:
            return None
        log_levels = list(map(lambda x: x.level, self.comments))
        return LogLevel.highest_level(log_levels)