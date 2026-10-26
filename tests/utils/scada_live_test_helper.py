import shutil
import socket
import time
import typing
from typing import Any, Optional

from pathlib import Path

from gwproactor import App, AppSettings
from gwproactor.config import Paths
from gwproactor_test.instrumented_proactor import InstrumentedProactor, MinRangeTuple
from gwproactor_test.tree_live_test_helper import TreeLiveTest
from gwproto.messages import EventT, ProblemEvent, ShutdownEvent
from result import Result

from gwsproto.data_classes.components.web_server_component import WebServerComponent
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.enums import SeasonalStorageMode, ServiceMode, SiegLoopStrategy
from gwsproto.named_types import DispatchHold, OperationalParams, TaDeed
from gwsproto.property_format import LeftRightDotStr
from tests.conftest import TEST_HARDWARE_LAYOUT_PATH
from ltn_app import LtnApp
from weather_source import WeatherSourceKind
from scada2_app import Scada2App
from scada_app import ScadaApp

from actors.config import DEFAULT_TA_DEED_FILE
from actors.hydronic.shared import dispatch_channels
from actors.scada import Scada
from sema_to_dc import load_layout


def fixture_deed_path(layout: HydronicLayout) -> Optional[Path]:
    """The ta.deed fixture in tests/config whose TaId is the layout's
    TerminalAsset GNodeId, or None when no fixture deed binds it."""
    for path in sorted(TEST_HARDWARE_LAYOUT_PATH.parent.glob("*.ta.deed.json")):
        deed = TaDeed.model_validate_json(path.read_text())
        if deed.TaId == layout.terminal_asset_g_node_id:
            return path
    return None


def ops_word_with(
    source: Path,
    dest: Path,
    *,
    standby: Optional[bool] = None,
    service_mode: Optional[ServiceMode] = None,
    seasonal_storage_mode: Optional[SeasonalStorageMode] = None,
    sieg_loop_strategy: Optional[SiegLoopStrategy] = None,
    uses_backup_when_cold: Optional[bool] = None,
    scada_alias: Optional[LeftRightDotStr] = None,
    service_contract_broken: Optional[bool] = None,
) -> Path:
    """The fixture ops word at `source`, authored with the named selections
    and written to `dest` for a scada to read. Standby brings the operator
    hold with it (axiom 3); every field not named stays as the fixture
    states it. The word is rebuilt through OperationalParams, so a selection
    the word refuses fails here, not at boot."""
    word = OperationalParams.model_validate_json(source.read_text())
    changes: dict[str, object] = {}
    if standby is not None:
        changes["Standby"] = standby
    if standby is not None or service_contract_broken is not None:
        changes["DispatchHold"] = DispatchHold(
            OperatorHold=word.DispatchHold.OperatorHold or bool(standby),
            ServiceContractBroken=(
                word.DispatchHold.ServiceContractBroken
                if service_contract_broken is None
                else service_contract_broken
            ),
        )
    if service_mode is not None:
        changes["ServiceMode"] = service_mode
    if uses_backup_when_cold is not None:
        changes["UsesBackupWhenCold"] = uses_backup_when_cold
    if scada_alias is not None:
        changes["ScadaAlias"] = scada_alias
    family_changes: dict[str, object] = {}
    if seasonal_storage_mode is not None:
        family_changes["SeasonalStorageMode"] = seasonal_storage_mode
    if sieg_loop_strategy is not None:
        family_changes["SiegLoopStrategy"] = sieg_loop_strategy
    if family_changes:
        changes["FamilyParams"] = word.FamilyParams.model_copy(update=family_changes)
    # model_copy does not validate; the round trip through the wire form does.
    authored = OperationalParams.model_validate_json(
        word.model_copy(update=changes).model_dump_json(by_alias=True, exclude_none=True)
    )
    dest.write_text(authored.model_dump_json(by_alias=True, exclude_none=True))
    return dest


def fixture_config_dir(ops_path: Path, layout_name: str) -> Path:
    """A scada config dir laid out in the authored ops word's directory:
    the layout (a fixture name, or the path of a layout a test authored)
    and the fixture deed issued to its terminal asset, under the names a
    scada resolves. Returns the layout path. The fixture dir itself is
    never written: a boot off it would resolve its deed there and write
    one."""
    config_dir = ops_path.parent
    layout_path = config_dir / Path(Paths(name="scada").hardware_layout).name
    source = TEST_HARDWARE_LAYOUT_PATH.parent / layout_name
    if source.resolve() != layout_path.resolve():
        shutil.copyfile(source, layout_path)
    layout = load_layout(layout_path, ops_path)
    deed_path = fixture_deed_path(layout)
    assert deed_path is not None, "no fixture deed binds this layout's terminal asset"
    shutil.copyfile(deed_path, config_dir / DEFAULT_TA_DEED_FILE)
    return layout_path


def fresh_buffer(scada: Scada, for_s: int = 3600) -> None:
    """Stamp the family's dispatch channels as read now, so the scada is not
    blind for the test's duration. The suite simulates no tank module, so
    nothing posts buffer temperatures; this stands in for that sensor. A
    simulated tank module retires it."""
    channels = dispatch_channels(scada.layout)
    stamp = int((time.time() + for_s) * 1000)
    for name in channels:
        scada._data.latest_channel_unix_ms[name] = stamp
    scada.note_reading_for_buffer_fresh_once()  # as the reading path would


def free_port() -> int:
    """A TCP port nothing listens on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


class RecordingProactor(InstrumentedProactor):
    """An instrumented proactor that keeps the shutdown and problem events
    it generates, and names them in its summary, so a scada that stopped
    says why in the failure dump."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.recorded_events: list[ShutdownEvent | ProblemEvent] = []

    def generate_event(self, event: EventT) -> Result[bool, Exception]:
        if isinstance(event, (ShutdownEvent, ProblemEvent)):
            self.recorded_events.append(event)
        return super().generate_event(event)

    def summary_str(self, *, ack_tracking: bool = False) -> str:
        s = super().summary_str(ack_tracking=ack_tracking)
        s += "Shutdown and problem events:\n"
        for event in self.recorded_events:
            if isinstance(event, ShutdownEvent):
                s += f"  {event.TypeName}: {event.Reason}\n"
            else:
                s += f"  {event.TypeName}: {event.Summary}: {event.Details}\n"
        return s


class ScadaLiveTest(TreeLiveTest):
    UPLOADER_LONG_NAME = "test_uploader"
    reassigned_web_servers: set[int]

    @classmethod
    def parent_app_type(cls) -> type[LtnApp]:
        return LtnApp

    @property
    def parent_app(self) -> LtnApp:
        return typing.cast(LtnApp, self._parent_app)

    @classmethod
    def child_app_type(cls) -> type[ScadaApp]:
        return ScadaApp

    @property
    def child_app(self) -> ScadaApp:
        return typing.cast(ScadaApp, self._child_app)

    @property
    def child1_app(self) -> ScadaApp:
        return self.child_app

    @classmethod
    def child2_app_type(cls) -> type[Scada2App]:
        return Scada2App

    @property
    def child2_app(self) -> Scada2App:
        return typing.cast(Scada2App, self._child2_app)

    @classmethod
    def test_layout_path(cls) -> Path:
        return TEST_HARDWARE_LAYOUT_PATH

    def __init__(self,
        *,
        layout: Optional[HydronicLayout] = None,
        child_layout: Optional[HydronicLayout] = None,
        child1_layout: Optional[HydronicLayout] = None,
        child2_layout: Optional[HydronicLayout] = None,
        parent_layout: Optional[HydronicLayout] = None,
        child1_simulated: bool = True,
        child2_simulated: bool = True,
        ops_path: Optional[Path] = None,
        **kwargs: typing.Any
    ) -> None:
        self.reassigned_web_servers = set()

        kwargs["child_app_settings"] = kwargs.get(
            "child_app_settings",
            self.child_app_type()
            .app_settings_type()()
            .with_paths_name(
                self.child_app_type().paths_name()
            )
        )
        # The conftest seeds every config dir with the Nolan ops file; a
        # test on another layout names its pair's ops artifact here, since
        # the primary scada's actors read ops from the settings path, not
        # from the layout object handed in.
        if ops_path is not None:
            kwargs["child_app_settings"].paths.operational_params = ops_path
        # Likewise the deed, which binds one terminal asset: a test on
        # another layout gets the fixture deed issued to that layout's
        # terminal asset, copied over the seeded one. A test that removed
        # the seeded deed stays without one.
        primary_layout = child1_layout or child_layout or layout
        # The suite never reaches a live weather API.
        kwargs["child_app_settings"].weather_source = WeatherSourceKind.Sim
        seeded_deed = Path(kwargs["child_app_settings"].paths.tadeed)
        if primary_layout is not None and seeded_deed.exists():
            deed_path = fixture_deed_path(primary_layout)
            if deed_path is not None:
                shutil.copyfile(deed_path, seeded_deed)
        kwargs["child2_app_settings"] = kwargs.get(
            "child2_app_settings",
            self.child2_app_type()
            .app_settings_type()()
            .with_paths_name(
                self.child2_app_type().paths_name()
            )
        )
        super().__init__(
            layout=layout,
            child_layout=child_layout,
            child1_layout=child1_layout,
            child2_layout=child2_layout,
            parent_layout=parent_layout,
            **kwargs
        )

    def _make_app(self, app_type: type[App], app_settings: Optional[AppSettings], **kwargs: Any) -> App:
        """Every app runs a RecordingProactor, and every web server its
        layout declares serves on a port nothing else holds: a fixed web
        port is a deployed-box fact, and a test never depends on what
        listens on the laptop. The base class instantiates and starts the
        apps inside its constructor, so this is the one place before that."""
        app = super()._make_app(app_type, app_settings, **kwargs)
        app.sub_types.proactor_type = RecordingProactor
        for ws in app.config.layout.get_components_by_type(WebServerComponent):
            if id(ws.web_server_gt) not in self.reassigned_web_servers:
                self.reassigned_web_servers.add(id(ws.web_server_gt))
                ws.web_server_gt.Port = free_port()
        return app

    # noinspection PyMethodMayBeStatic
    def default_quiescent_total_children_events(self) -> int:
        return sum(
            [
                4,  # child2 startup, connect, subscribe, peer active
                1,  # child1 startup
                6,  # child1 (parent, child2, admin) x (connect, subscribe)
                2,  # child1 (parent, child2) x peer active
            ]
        )

    # noinspection PyMethodMayBeStatic
    def default_quiesecent_parent_pending(
        self,
        exp_child_persists: Optional[int | MinRangeTuple] = None,
        exp_total_children_events: Optional[int] = None,
    ) -> int:
        return 0  # LTN does not attempt to forward child events.

    # noinspection PyMethodMayBeStatic
    def default_quiesecent_parent_persists(
        self,
        exp_parent_pending: Optional[int | MinRangeTuple] = None,
        exp_child_persists: Optional[int | MinRangeTuple] = None,
    ) -> int:
        return 4 # startup, connect, subscribed, child1 active; LTN does not
                 #   persist child events

    async def await_parent_at_rest(
        self,
        *,
        exp_parent_pending: int | MinRangeTuple,
        exp_parent_persists: Optional[int | MinRangeTuple] = None,
        exp_total_children_events: Optional[int] = None,  # noqa: ARG002
        exact: bool = False,
        caller_depth: int = 4,
    ) -> None:
        await super().await_parent_at_rest(
            exp_parent_pending=exp_parent_pending,
            exp_parent_persists=exp_parent_persists,
            exact=exact,
            caller_depth=caller_depth + 1,
        )
        def _child_events_received() -> int:
            rcv = 0
            scada_link_stats = self.parent.stats.link(self.parent.downstream_client)
            for event_src_dict in scada_link_stats.event_counts.values():
                rcv += sum(event_src_dict.values())
            return rcv

        await self.await_for(
            lambda: _child_events_received() >= exp_total_children_events,
            (
                f"ERROR waiting for LTN to receive {exp_total_children_events} "
                "told child events"
            ),
            caller_depth=caller_depth,
        )
