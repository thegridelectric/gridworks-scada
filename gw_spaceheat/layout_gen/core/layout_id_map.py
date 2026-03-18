"""
LayoutIDMap: indexed view of an existing hardware layout.

Loads a hardware-layout.json (local or remote) and builds lookup maps
from names/aliases → IDs for CACs, components, nodes, and channels.

Used by LayoutDb to reuse stable IDs when regenerating layouts.
Represents "what exists" in a deployed system.
"""

import json
import subprocess
from pathlib import Path

from gwsproto.enums import MakeModel
from gwsproto.errors import DcError
from gwsproto.property_format import SpaceheatName, UUID4Str
from gwsproto.type_helpers import CACS_BY_MAKE_MODEL


class LayoutIDMap:
    """
    Lookup map for IDs in an existing hardware layout.
    """
    REMOTE_HARDWARE_LAYOUT_PATH: str = "/home/pi/.config/gridworks/scada/hardware-layout.json"

    cacs_by_alias: dict[str, UUID4Str] # uses MakeModel if not Unkonw or display name
    components_by_alias: dict[str, UUID4Str] # uses display name for now, OFI
    nodes_by_name: dict[SpaceheatName, UUID4Str]
    channels_by_name: dict[SpaceheatName, UUID4Str]
    derived_channels_by_name: dict[str, UUID4Str]
    g_nodes: dict[str, dict]

    def __init__(self, d: dict | None = None):
        self.cacs_by_alias = {}
        self.components_by_alias = {}
        self.nodes_by_name = {}
        self.channels_by_name = {}
        self.derived_channels_by_name = {}
        self.g_nodes = {}

        if not d:
            return
        for k, v in d.items():
                if isinstance(v, dict) and "GNodeId" in v:
                    self.g_nodes[k] = v
                elif k == "ShNodes":
                        for node in v:
                            try:
                                self.add_node(
                                    node["ShNodeId"],
                                    node["Name"],
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{node}. Error: {type(e)}, <{e}>"
                                )
                elif k == "DataChannels":
                        for channel in v:
                            try:
                                self.add_channel(
                                    channel["Id"],
                                    channel["Name"]
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{channel}. Error: {type(e)}, <{e}>"
                                )
                elif k == "DerivedChannels":
                        for channel in v:
                            try:
                                self.add_derived_channel(
                                    channel["Id"],
                                    channel["Name"]
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{channel}. Error: {type(e)}, <{e}>"
                                )

                elif k.lower().endswith("cacs"):
                        for cac in v:
                            try:
                                self.add_cacs_by_alias(
                                    cac["ComponentAttributeClassId"],
                                    cac["MakeModel"],
                                    cac["DisplayName"],
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{cac}. Error: {type(e)}, <{e}>"
                                )

                elif k.lower().endswith("components"):
                        for component in v:
                            try:
                                self.add_component(
                                    component["ComponentId"],
                                    component["DisplayName"],
                                )
                            except Exception as e:
                                raise Exception(
                                    f"ERROR in LayoutIDMap() for {k}:{component}. Error: {type(e)}, <{e}>"
                                )

    def add_cacs_by_alias(self, id_: str, make_model_: str, display_name_: str):
        if make_model_ == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL.value:
            self.cacs_by_alias[display_name_] = id_
        else:
            if CACS_BY_MAKE_MODEL[make_model_] != id_:
                raise DcError(f"MakeModel {make_model_} does not go with {id_}")
            self.cacs_by_alias[make_model_] = id_

    def add_component(self, id_: str, alias: str):
        self.components_by_alias[alias] = id_

    def add_node(self, id_: str, name: str):
        self.nodes_by_name[name] = id_
    
    def add_channel(self, id_: str, name: str):
        self.channels_by_name[name] = id_

    def add_derived_channel(self, id_: str, name: str):
        self.derived_channels_by_name[name] = id_

    @classmethod
    def from_path(cls, path: Path) -> "LayoutIDMap":
        with path.open() as f:
            return LayoutIDMap(json.loads(f.read()))

    @classmethod
    def from_rclone(
        cls, rclone_name: str,
        upload_dir: Path,
        remote_path: str | Path = REMOTE_HARDWARE_LAYOUT_PATH
    ) -> "LayoutIDMap":
        if not upload_dir.exists():
            upload_dir.mkdir(parents=True)
        dest_path = upload_dir / f"{rclone_name}.uploaded.json"
        upload = [
            "rclone",
            "copyto",
            f"{rclone_name}:{str(remote_path)}",
            f"{dest_path}",
        ]
        print(f"Running upload command:\n\n{' '.join(upload)}\n")
        result = subprocess.run(upload, capture_output=True)
        if result.returncode != 0:
            print(f"Command output:\n[\n{result.stderr.decode('utf-8')}\n]")
            raise RuntimeError(
                f"ERROR. Command <{' '.join(upload)}> failed with returncode:{result.returncode}"
            )
        return cls.from_path(dest_path)
