from abc import ABC
from abc import abstractmethod

from gwproactor import AppInterface

from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from data_classes.house_0_layout import House0Layout


class ScadaAppInterface(AppInterface, ABC):
    @property
    @abstractmethod
    def settings(self) -> ScadaSettings:
        raise NotImplementedError

    @property
    @abstractmethod
    def prime_actor(self) -> ScadaInterface:
        raise NotImplementedError

    @property
    @abstractmethod
    def scada(self) -> ScadaInterface:
        raise NotImplementedError


    @property
    @abstractmethod
    def hardware_layout(self) -> House0Layout:
        raise NotImplementedError