from abc import ABC
from abc import abstractmethod

from gwproactor import AppInterface

from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from gwsproto.data_classes.hydronic_layout import HydronicLayout


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
    def hardware_layout(self) -> HydronicLayout:
        raise NotImplementedError