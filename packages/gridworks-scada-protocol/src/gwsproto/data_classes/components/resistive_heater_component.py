"""ResistiveHeaterComponent definition"""

from typing import Any

from gwsproto.data_classes.components.component import Component
from gwsproto.named_types import ResistiveHeaterComponentGt


class ResistiveHeaterComponent(Component[ResistiveHeaterComponentGt, Any]): ...
