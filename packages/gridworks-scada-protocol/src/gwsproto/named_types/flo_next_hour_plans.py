from typing import List, Literal

from pydantic import BaseModel


class FloNextHourPlans(BaseModel):
    """Plan output from FLO for the next hour(s) after market clear."""

    ExpectedStorageKwhAtHour1: float
    HourlyHpKwhElPlan: List[float]  # HP kWh per hour for each hour in the plan
    TypeName: Literal["flo.next.hour.plans"] = "flo.next.hour.plans"
    Version: Literal["000"] = "000"
