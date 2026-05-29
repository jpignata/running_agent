from __future__ import annotations

from datetime import datetime


def human_datetime(value: str | None) -> str:
    if not value:
        return "unknown time"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return value
    return parsed.strftime("%A, %b %-d at %-I:%M %p")
