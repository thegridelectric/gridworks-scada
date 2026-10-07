from abc import ABC
from abc import abstractmethod
from pathlib import Path

from gwproactor import AppInterface

from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from clock import Clock
from weather_source import WeatherSource
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
    @abstractmethod
    def clock(self) -> Clock:
        """The one clock every actor reads plant time from."""
        raise NotImplementedError

    @property
    @abstractmethod
    def weather_source(self) -> WeatherSource:
        """Where the derived generator and the LTN get their weather forecast."""
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
        from its ta.deed; UnValidated when it holds none. An UnValidated
        scada refuses every LTN contract offer."""
        deed = self.ta_deed
        if deed is None:
            return TaValidationState.UnValidated
        return deed.ValidationState

    @property
    def deed_on_file(self) -> TaDeed | None:
        """The ta.deed instance at settings.paths.tadeed, whatever terminal
        asset it names, or None when there is no file."""
        deed_path = Path(self.settings.paths.tadeed)
        if not deed_path.exists():
            return None
        return TaDeed.model_validate_json(deed_path.read_text())

    @property
    def ta_deed(self) -> TaDeed | None:
        """This terminal asset's deed: the one on file when its TaId is the
        layout's TerminalAsset GNodeId. None when there is no file, and
        None when the file's deed names another terminal asset."""
        deed = self.deed_on_file
        if deed is None or deed.TaId != self.hardware_layout.terminal_asset_g_node_id:
            return None
        return deed

    @abstractmethod
    def upstream_is_send_capable(self) -> bool:
        """The upstream link can carry a publish to the broker: connected
        and fully subscribed, with or without a peer."""
        raise NotImplementedError
