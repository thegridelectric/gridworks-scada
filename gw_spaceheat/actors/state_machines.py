"""The state machines a scada hosts, declared from its layout and ops word.

The scada has no view of its running actors' machines; the declaration is
derived from what selects them: the actor class of each node, a relay
config's StateType, the pico roster, and the ops word's selection of the
local-control and leaf-ally machines (`local_control_loader.py`,
`leaf_ally_loader.py`). A machine's reports name it by MachineHandle, whose
last dotted segment is the hosting node's Name."""

from gwsproto.data_classes.components import (
    PicoBtuMeterComponent,
    PicoFlowModuleComponent,
    PicoTankModuleComponent,
    SimPicoBtuMeterComponent,
    SimPicoTankModuleComponent,
)
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    ActorClass,
    FiveVBossState,
    HpBossState,
    LeafAllyAllTanksState,
    LeafAllyBufferOnlyState,
    LocalControlAllTanksState,
    LocalControlBufferOnlyState,
    LocalControlTopState,
    MainAutoState,
    NolanLcBufferOnlyState,
    PicoCyclerState,
    SeasonalStorageMode,
    ServiceMode,
    SiegValveState,
    SinglePicoState,
    SpruceHackHpState,
    TopState,
)
from gwsproto.enums.gw_str_enum import SemaEnum
from gwsproto.named_types import GwStateMachine, NolanLayout, OperationalParams

from actors.relay import STATE_ENUM_BY_NAME

PICO_COMPONENTS = (
    PicoBtuMeterComponent,
    SimPicoBtuMeterComponent,
    PicoFlowModuleComponent,
    PicoTankModuleComponent,
    SimPicoTankModuleComponent,
)

# One machine per node for the actor classes whose machine the class fixes.
MACHINE_BY_ACTOR_CLASS: dict[ActorClass, type[SemaEnum]] = {
    ActorClass.PrimaryScada: TopState,
    ActorClass.HpBoss: HpBossState,
    ActorClass.FiveVBoss: FiveVBossState,
    ActorClass.PicoCycler: PicoCyclerState,
    ActorClass.SiegLoop: SiegValveState,
    ActorClass.HpWatch: SpruceHackHpState,
    ActorClass.LocalControl: LocalControlTopState,
}


def declaration(node: ShNode, enum: type[SemaEnum]) -> GwStateMachine:
    return GwStateMachine(
        NodeName=node.Name,
        StateEnum=enum.enum_name(),
        StateEnumVersion=enum.enum_version(),
    )


def relay_state_enum(node: ShNode) -> type[SemaEnum]:
    """The relay's state enum, from its config's StateType (`actors/relay.py`)."""
    cfg = next(x for x in node.component.gt.ConfigList if x.ActorName == node.name)
    return STATE_ENUM_BY_NAME[cfg.StateType]


def leaf_ally_state_enum(layout: HydronicLayout, ops: OperationalParams) -> type[SemaEnum]:
    if isinstance(layout.sema_layout, NolanLayout):
        return LeafAllyBufferOnlyState
    if ops.FamilyParams.SeasonalStorageMode == SeasonalStorageMode.AllTanks:
        return LeafAllyAllTanksState
    return LeafAllyBufferOnlyState


def local_control_normal_enum(
    layout: HydronicLayout, ops: OperationalParams
) -> type[SemaEnum] | None:
    """The machine on the local control's normal node, None under standby
    (the standby machine runs on the local-control node alone)."""
    if ops.Standby or ops.ServiceMode != ServiceMode.Heating:
        return None
    if isinstance(layout.sema_layout, NolanLayout):
        return NolanLcBufferOnlyState
    if ops.FamilyParams.SeasonalStorageMode == SeasonalStorageMode.AllTanks:
        return LocalControlAllTanksState
    return LocalControlBufferOnlyState


def declared_state_machines(layout: HydronicLayout, ops: OperationalParams) -> list[GwStateMachine]:
    machines: list[GwStateMachine] = [declaration(layout.auto_node, MainAutoState)]
    normal_enum = local_control_normal_enum(layout, ops)
    if normal_enum is not None:
        machines.append(declaration(layout.local_control_normal_node, normal_enum))
    for node in layout.nodes.values():
        if layout.node_disabled(node.name):
            continue
        if node.ActorClass in MACHINE_BY_ACTOR_CLASS:
            machines.append(declaration(node, MACHINE_BY_ACTOR_CLASS[node.ActorClass]))
        elif node.ActorClass == ActorClass.Relay:
            machines.append(declaration(node, relay_state_enum(node)))
        elif node.ActorClass == ActorClass.LeafAlly:
            machines.append(declaration(node, leaf_ally_state_enum(layout, ops)))
        elif isinstance(getattr(node, "component", None), PICO_COMPONENTS):
            machines.append(declaration(node, SinglePicoState))
    return sorted(machines, key=lambda m: m.NodeName)
