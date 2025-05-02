"""GridWorks Scada functionality beyond proactor.AppInterface"""

from abc import ABC
from abc import abstractmethod

from gwproactor import ActorInterface
from actors.scada_data import ScadaData


class ScadaInterface(ActorInterface, ABC):

    @property
    @abstractmethod
    def data(self) -> ScadaData:
        raise NotImplementedError

