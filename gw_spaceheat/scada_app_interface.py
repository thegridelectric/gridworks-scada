from abc import ABC
from abc import abstractmethod
from pathlib import Path

from gwproactor import AppInterface

from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.enums import TaValidationState
from gwsproto.named_types import TaDeed


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
        """The plant is simulated: the layout carries a simulated device.

        Its one job is the sim-time bridge in Scada, deciding whether the
        scada reads time.time() or the time coordinator's simulated
        timestep. It is NOT the place to ask whether the scada may trade
        (validation_state) or which silicon to drive (the layout's board
        record, ScadaBoardComponent.simulated).
        """
        return self.hardware_layout.has_simulated_component()

    @property
    def validation_state(self) -> TaValidationState:
        """What a TaValidator has attested about this terminal asset, read
        from the ta.deed instance at settings.paths.tadeed; UnValidated
        when there is no deed. An UnValidated scada refuses every LTN
        contract offer."""
        deed_path = Path(self.settings.paths.tadeed)
        if not deed_path.exists():
            return TaValidationState.UnValidated
        return TaDeed.model_validate_json(deed_path.read_text()).ValidationState
