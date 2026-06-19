from __future__ import annotations

from typing import Any

NUMERIC_TYPES = (int, float)
MIN_REASONABLE_HR = 40
MAX_REASONABLE_HR = 240


def observed_max_heart_rate(activities: list[dict[str, Any]]) -> int | None:
    values: list[float] = []
    for activity in activities:
        _append_hr(values, activity.get("max_heartrate"))
        for lap in activity.get("laps") or []:
            if isinstance(lap, dict):
                _append_hr(values, lap.get("max_heartrate"))
    return int(round(max(values))) if values else None


def heart_rate_percent(heart_rate: Any, max_heart_rate: int | float | None) -> int | None:
    if not isinstance(heart_rate, NUMERIC_TYPES) or not isinstance(max_heart_rate, NUMERIC_TYPES):
        return None
    if not _reasonable_hr(float(heart_rate)) or not _reasonable_hr(float(max_heart_rate)):
        return None
    if heart_rate > max_heart_rate:
        return None
    return int(round(float(heart_rate) / float(max_heart_rate) * 100))


def format_heart_rate(heart_rate: Any, max_heart_rate: int | float | None = None) -> str:
    if not isinstance(heart_rate, NUMERIC_TYPES):
        return "n/a"
    percent = heart_rate_percent(heart_rate, max_heart_rate)
    if percent is None:
        return f"{heart_rate:.0f} bpm"
    return f"{heart_rate:.0f} bpm ({percent}% max HR)"


def _append_hr(values: list[float], value: Any) -> None:
    if isinstance(value, NUMERIC_TYPES) and _reasonable_hr(float(value)):
        values.append(float(value))


def _reasonable_hr(value: float) -> bool:
    return MIN_REASONABLE_HR <= value <= MAX_REASONABLE_HR
