"""What board and MicroPython release a pico-fed actor's pico reports in
its params post, held against what the layout says the house was
provisioned with.

A pico posts its params at every boot and the pico-cycler reboots picos,
so a standing difference is reported once per scada run, not once per post.

Pure: nothing is sent from here. The actor sends a warning for each
difference `differences` returns, and a debug glitch for the post
`first_match` accepts."""

from typing import NamedTuple, Optional

from gwsproto.enums import PicoBoardVariant


class PicoIdentityDifference(NamedTuple):
    """One field of a params post that differs from the layout's component.
    No sema word carries this; a word for a pico identity report would
    retire it."""

    field: str  # the component field name: PicoBoardVariant or MicropythonVersion
    layout_value: str
    posted_value: str

    def summary(self, actor_name: str) -> str:
        return f"{actor_name} pico {self.field} differs from the layout"

    def details(self, hw_uid: str) -> str:
        return (
            f"pico {hw_uid} posted {self.posted_value}; "
            f"the layout says {self.layout_value}"
        )


class PicoIdentity:
    """The layout's PicoBoardVariant and MicropythonVersion for one pico.
    A layout that states no MicropythonVersion holds the post to none."""

    def __init__(
        self,
        board_variant: PicoBoardVariant,
        micropython_version: Optional[str],
    ) -> None:
        self.board_variant = board_variant
        self.micropython_version = micropython_version
        self.reported: set[PicoIdentityDifference] = set()
        self.match_reported = False

    def differences(
        self, posted_board_variant: PicoBoardVariant, posted_micropython_version: str
    ) -> list[PicoIdentityDifference]:
        """The differences between this post and the layout that no earlier
        post has already shown; records them."""
        found: list[PicoIdentityDifference] = []
        if posted_board_variant != self.board_variant:
            found.append(
                PicoIdentityDifference(
                    field="PicoBoardVariant",
                    layout_value=self.board_variant.value,
                    posted_value=posted_board_variant.value,
                )
            )
        if (
            self.micropython_version is not None
            and posted_micropython_version != self.micropython_version
        ):
            found.append(
                PicoIdentityDifference(
                    field="MicropythonVersion",
                    layout_value=self.micropython_version,
                    posted_value=posted_micropython_version,
                )
            )
        new = [d for d in found if d not in self.reported]
        self.reported.update(new)
        return new

    def matches(
        self, posted_board_variant: PicoBoardVariant, posted_micropython_version: str
    ) -> bool:
        """Whether this post agrees with the layout on every field the
        layout states."""
        return posted_board_variant == self.board_variant and (
            self.micropython_version is None
            or posted_micropython_version == self.micropython_version
        )

    def first_match(
        self, posted_board_variant: PicoBoardVariant, posted_micropython_version: str
    ) -> bool:
        """True for the first post of the scada run that matches the layout;
        records it."""
        if self.match_reported or not self.matches(
            posted_board_variant, posted_micropython_version
        ):
            return False
        self.match_reported = True
        return True
