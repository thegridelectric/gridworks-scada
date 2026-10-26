"""The backup axioms shared by the layout words: the backup command node
exists exactly when Hydronic.Backup does, and the relays a backup names are
Relay ShNodes. One implementation here; each type's check_axiom_<n> supplies
its own label."""

from typing import Iterable, Optional, Union

from gwsproto.enums import ActorClass
from gwsproto.named_types.boiler_backup import BoilerBackup
from gwsproto.named_types.element_backup import ElementBackup
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.names.core.node_names import CoreNodeNames


def check_backup_node(
    nodes: Iterable[SpaceheatNodeGt],
    backup: Optional[Union[BoilerBackup, ElementBackup]],
    axiom: str,
) -> None:
    """b. With a Backup, exactly one NoActor ShNode named "backup".
    c. Without one, no ShNode named "backup"."""
    named = [n for n in nodes if n.Name == CoreNodeNames.local_control_backup]
    if backup is not None:
        if len(named) != 1 or named[0].ActorClass != ActorClass.NoActor:
            raise ValueError(
                f"{axiom} failed: Hydronic.Backup is present, so exactly one ShNode "
                "'backup' with ActorClass NoActor SHALL exist."
            )
    elif named:
        raise ValueError(
            f"{axiom} failed: Hydronic.Backup is absent, so no ShNode SHALL be "
            "named 'backup'."
        )


def check_backup_relays(
    nodes: Iterable[SpaceheatNodeGt],
    backup: Optional[Union[BoilerBackup, ElementBackup]],
    axiom: str,
) -> None:
    """Every relay the backup names is an ShNode with ActorClass Relay."""
    if backup is None:
        return
    if isinstance(backup, BoilerBackup):
        names = [backup.FailsafeRelayName, backup.AquastatCtrlRelayName]
    else:
        names = list(backup.ElementRelayNames)
    relays = {n.Name for n in nodes if n.ActorClass == ActorClass.Relay}
    for name in names:
        if name not in relays:
            raise ValueError(
                f"{axiom} failed: the backup names {name!r}, which is not an "
                "ShNode with ActorClass Relay."
            )
