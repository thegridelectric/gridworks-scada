from abc import ABC
from abc import abstractmethod

from gwproactor import AppInterface

from actors.ltn.config import LtnSettings
from clock import Clock
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.named_types import OperationalParams
from weather_source import WeatherSource


class LtnAppInterface(AppInterface, ABC):
    """What the LTN actor reads from the app that hosts it."""

    @property
    @abstractmethod
    def settings(self) -> LtnSettings:
        raise NotImplementedError

    @property
    @abstractmethod
    def hardware_layout(self) -> HydronicLayout:
        raise NotImplementedError

    @property
    @abstractmethod
    def clock(self) -> Clock:
        """The one clock the LTN reads plant time from."""
        raise NotImplementedError

    @property
    @abstractmethod
    def weather_source(self) -> WeatherSource:
        """Where the LTN gets the forecast its FLO runs on."""
        raise NotImplementedError

    @property
    @abstractmethod
    def operational_params(self) -> OperationalParams:
        """The house's gw.operational.params, read from the LTN box's config folder."""
        raise NotImplementedError
