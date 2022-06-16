"""Makes gt.spaceheat.status.100 type"""

import json
from typing import List
from schema.gt.gt_spaceheat_status.gt_spaceheat_status import GtSpaceheatStatus
from schema.errors import MpSchemaError

from schema.gt.gt_spaceheat_sync_single.gt_spaceheat_sync_single_maker \
    import GtSpaceheatSyncSingle, GtSpaceheatSyncSingle_Maker
from schema.gt.gt_spaceheat_async_single.gt_spaceheat_async_single_maker \
    import GtSpaceheatAsyncSingle, GtSpaceheatAsyncSingle_Maker


class GtSpaceheatStatus_Maker():
    type_alias = 'gt.spaceheat.status.100'

    def __init__(self,
                 about_g_node_alias: str,
                 slot_start_unix_s: int,
                 reporting_period_s: int,
                 async_status_list: List[GtSpaceheatAsyncSingle],
                 sync_status_list: List[GtSpaceheatSyncSingle]):

        tuple = GtSpaceheatStatus(AboutGNodeAlias=about_g_node_alias,
                                  SlotStartUnixS=slot_start_unix_s,
                                  ReportingPeriodS=reporting_period_s,
                                  AsyncStatusList=async_status_list,
                                  SyncStatusList=sync_status_list,
                                  )
        tuple.check_for_errors()
        self.tuple = tuple

    @classmethod
    def tuple_to_type(cls, tuple: GtSpaceheatStatus) -> str:
        tuple.check_for_errors()
        return tuple.as_type()

    @classmethod
    def type_to_tuple(cls, t: str) -> GtSpaceheatStatus:
        try:
            d = json.loads(t)
        except TypeError:
            raise MpSchemaError('Type must be string or bytes!')
        if not isinstance(d, dict):
            raise MpSchemaError(f"Deserializing {t} must result in dict!")
        return cls.dict_to_tuple(d)

    @classmethod
    def dict_to_tuple(cls, d: dict) -> GtSpaceheatStatus:
        if "AboutGNodeAlias" not in d.keys():
            raise MpSchemaError(f"dict {d} missing AboutGNodeAlias")
        if "SlotStartUnixS" not in d.keys():
            raise MpSchemaError(f"dict {d} missing SlotStartUnixS")
        if "ReportingPeriodS" not in d.keys():
            raise MpSchemaError(f"dict {d} missing ReportingPeriodS")
        if "AsyncStatusList" not in d.keys():
            raise MpSchemaError(f"dict {d} missing AsyncStatusList")
        if "SyncStatusList" not in d.keys():
            raise MpSchemaError(f"dict {d} missing SyncStatusList")
        if not isinstance(d["SyncStatusList"], list):
            raise MpSchemaError(f"d['SyncStatusList'] {d['SyncStatusList']} must be a list!")
        sync_status_list = []
        for sync_status in d["SyncStatusList"]:
            sync_status_list.append(GtSpaceheatSyncSingle_Maker.dict_to_tuple(sync_status))
        d["SyncStatusList"] = sync_status_list
        if not isinstance(d["AsyncStatusList"], list):
            raise MpSchemaError(f"d['AsyncStatusList'] {d['AsyncStatusList']} must be a list!")
        async_status_list = []
        for async_status in d["AsyncStatusList"]:
            async_status_list.append(GtSpaceheatAsyncSingle_Maker.dict_to_tuple(async_status))
        d["AsyncStatusList"] = async_status_list

        tuple = GtSpaceheatStatus(AboutGNodeAlias=d["AboutGNodeAlias"],
                                  SlotStartUnixS=d["SlotStartUnixS"],
                                  ReportingPeriodS=d["ReportingPeriodS"],
                                  AsyncStatusList=d["AsyncStatusList"],
                                  SyncStatusList=d["SyncStatusList"],
                                  )
        tuple.check_for_errors()
        return tuple
