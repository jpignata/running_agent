from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

COACH_TIME_ZONE = ZoneInfo("America/New_York")


def coach_now() -> datetime:
    return datetime.now(COACH_TIME_ZONE)


def coach_today() -> date:
    return coach_now().date()


def in_coach_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=COACH_TIME_ZONE)
    return value.astimezone(COACH_TIME_ZONE)
