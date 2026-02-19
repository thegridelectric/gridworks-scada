"""ResistiveHeaterComponent definition"""

from gwsproto.data_classes.components.component import Component
from gwsproto.named_types import ResistiveHeaterCacGt, ResistiveHeaterComponentGt


class ResistiveHeaterComponent(
    Component[ResistiveHeaterComponentGt, ResistiveHeaterCacGt]
): ...
