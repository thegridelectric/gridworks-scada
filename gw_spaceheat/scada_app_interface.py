from abc import ABC
from abc import abstractmethod
from pathlib import Path

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

    @property
    def is_simulated(self) -> bool:
        """Is this scada NOT a real terminal asset? Simulated until proven
        real: real (False) requires BOTH a TaDeed present AND a layout with no
        simulated device. Gates system-level behavior only (the sim-time
        bridge); which silicon an actor drives is the layout's call, per
        device, via the board record (ScadaBoardComponent.simulated). The
        TaDeed is currently a fake placeholder file at settings.paths.tadeed.
        """
        if not Path(self.settings.paths.tadeed).exists():
            return True
        return self.hardware_layout.has_simulated_component()
