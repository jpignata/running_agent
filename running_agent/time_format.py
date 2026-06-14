from __future__ import annotations

from datetime import datetime, timedelta

from .coach_time import coach_now, in_coach_time


def human_datetime(value: str | None) -> str:
    if not value:
        return "unknown time"
    try:
        parsed = in_coach_time(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return value
    return _relative_datetime(parsed, in_coach_time(coach_now()))


def _relative_datetime(value: datetime, now: datetime) -> str:
    elapsed = now - value
    if elapsed < timedelta(minutes=1):
        return "just now"

    if elapsed < timedelta(hours=1):
        minutes = int(elapsed.total_seconds() // 60)
        return _plural(minutes, "minute")

    if elapsed < timedelta(hours=36):
        hours = int(elapsed.total_seconds() // 3600)
        return _plural(hours, "hour")

    if elapsed < timedelta(days=30):
        days = elapsed.days
        if days == 1:
            return "yesterday"
        return _plural(days, "day")

    return f"on {value.strftime('%A, %b %-d at %-I:%M %p')}"


def _plural(count: int, unit: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {unit}{suffix} ago"
