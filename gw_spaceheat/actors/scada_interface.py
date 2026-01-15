"""GridWorks Scada functionality beyond proactor.AppInterface"""

from abc import ABC
from abc import abstractmethod

from gwproactor import ActorInterface

from actors.contract_handler import ContractHandler
from actors.scada_data import ScadaData


class ScadaInterface(ActorInterface, ABC):
    LTN_MQTT: str = "gridworks_mqtt"
    LOCAL_MQTT: str = "local_mqtt"
    ADMIN_MQTT: str = "admin"

    @property
    @abstractmethod
    def data(self) -> ScadaData:
        raise NotImplementedError

    @property
    @abstractmethod
    def contract_handler(self) -> ContractHandler:
        raise NotImplementedError

