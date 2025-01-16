"""GridWorks Scada functionality beyond proactor.ServicesInterface"""

from abc import ABC
from abc import abstractmethod

from gwproactor import ActorInterface
from actors.config import ScadaSettings
from actors.scada_data import ScadaData
from gwproactor.proactor_interface import ServicesInterface

from data_classes.house_0_layout import House0Layout


class ScadaInterface(ServicesInterface, ActorInterface, ABC):

    @property
    @abstractmethod
    def settings(self) -> ScadaSettings:
        ...

    @property
    @abstractmethod
    def data(self) -> ScadaData:
        ...


    @property
    @abstractmethod
    def hardware_layout(self) -> House0Layout:
        ...
