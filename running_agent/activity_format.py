from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .workout_classifier import workout_classification_context


METERS_PER_MILE = 1609.344


def miles(activity: dict[str, Any]) -> float:
    return float(activity.get("distance") or 0) / METERS_PER_MILE


def activity_headline(activity: dict[str, Any]) -> str:
    name = activity.get("name") or "Run"
    distance = miles(activity)
    moving_time = int(activity.get("moving_time") or activity.get("elapsed_time") or 0)
    pace = _pace_per_mile(distance, moving_time)
    date = _friendly_date(activity.get("start_date_local") or activity.get("start_date"))
    hr = activity.get("average_heartrate")
    hr_note = f", avg HR {hr:.0f}" if isinstance(hr, int | float) else ""
    return f"{name}: {distance:.2f} mi on {date}, {pace}{hr_note}"


def detailed_activity_context(
    activity: dict[str, Any],
    max_laps: int = 40,
    target_date: date | None = None,
) -> str:
    lines = [activity_headline(activity), "", "Run details:"]
    lines.extend(_run_detail_lines(activity))
    if target_date:
        lines.append("")
        lines.append(workout_classification_context(activity, target_date))
    laps = activity.get("laps") or []
    if not laps:
        lines.append("No lap-by-lap data was included in the detailed Strava activity.")
        return "\n".join(lines)

    derived = _derived_workout_signals(activity)
    if derived:
        lines.append("")
        lines.extend(derived)

    lines.append("")
    lines.append("Lap data from Strava detailed activity:")
    lines.append("Lap | Distance | Moving | Elapsed | Pace | Avg HR | Max HR | Elev gain")
    for lap in laps[:max_laps]:
        lines.append(
            " | ".join(
                [
                    str(lap.get("lap_index") or lap.get("split") or "?"),
                    f"{miles(lap):.2f} mi",
                    _duration(int(lap.get("moving_time") or 0)),
                    _duration(int(lap.get("elapsed_time") or 0)),
                    _pace_per_mile(miles(lap), int(lap.get("moving_time") or 0)),
                    _heart_rate(lap.get("average_heartrate")),
                    _heart_rate(lap.get("max_heartrate")),
                    _feet(lap.get("total_elevation_gain")),
                ]
            )
        )
    if len(laps) > max_laps:
        lines.append(f"...{len(laps) - max_laps} additional laps omitted.")
    return "\n".join(lines)


def recent_runs_context(activities: list[dict[str, Any]], limit: int = 12) -> str:
    runs = [activity for activity in activities if activity.get("type") == "Run"]
    if not runs:
        return "No recent runs found."
    return "\n".join(f"- {activity_headline(activity)}" for activity in runs[:limit])


def _pace_per_mile(distance_miles: float, moving_time_seconds: int) -> str:
    if distance_miles <= 0 or moving_time_seconds <= 0:
        return "unknown pace"
    seconds_per_mile = int(moving_time_seconds / distance_miles)
    minutes, seconds = divmod(seconds_per_mile, 60)
    return f"{minutes}:{seconds:02d}/mi"


def _duration(seconds: int) -> str:
    if seconds <= 0:
        return "0:00"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _run_detail_lines(activity: dict[str, Any]) -> list[str]:
    details = [
        f"- Distance: {miles(activity):.2f} mi",
        f"- Moving time: {_duration(int(activity.get('moving_time') or 0))}",
        f"- Elapsed time: {_duration(int(activity.get('elapsed_time') or 0))}",
        f"- Average pace: {_pace_per_mile(miles(activity), int(activity.get('moving_time') or 0))}",
        f"- Elevation gain: {_feet(activity.get('total_elevation_gain'))}",
    ]
    high = activity.get("elev_high")
    low = activity.get("elev_low")
    if isinstance(high, int | float) and isinstance(low, int | float):
        details.append(f"- Elevation range: {_feet(low)} to {_feet(high)}")
    details.extend(
        [
            f"- Average HR: {_heart_rate(activity.get('average_heartrate'))}",
            f"- Max HR: {_heart_rate(activity.get('max_heartrate'))}",
            f"- Average cadence: {_cadence(activity.get('average_cadence'))}",
        ]
    )
    device = activity.get("device_name")
    if device:
        details.append(f"- Device: {device}")
    return details


def _derived_workout_signals(activity: dict[str, Any]) -> list[str]:
    laps = activity.get("laps") or []
    if not laps:
        return []

    lines = ["Derived workout signals:"]
    rep_lines = _quality_rep_lines(laps)
    recovery_lines = _recovery_lines(laps)

    if rep_lines:
        lines.append("- Quality-looking laps: " + "; ".join(rep_lines))
    if recovery_lines:
        lines.append("- Recovery-looking laps: " + "; ".join(recovery_lines))
    if len(lines) == 1:
        return []
    return lines


def _quality_rep_lines(laps: list[dict[str, Any]], limit: int = 12) -> list[str]:
    reps: list[str] = []
    for lap in laps:
        distance = miles(lap)
        moving_time = int(lap.get("moving_time") or 0)
        pace = _seconds_per_mile(distance, moving_time)
        if pace is None:
            continue
        if 0.18 <= distance <= 1.6 and pace <= 7 * 60:
            reps.append(
                f"lap {lap.get('lap_index') or lap.get('split')}: "
                f"{distance:.2f} mi at {_pace_per_mile(distance, moving_time)}, "
                f"avg HR {_heart_rate(lap.get('average_heartrate'))}"
            )
        if len(reps) >= limit:
            break
    return reps


def _recovery_lines(laps: list[dict[str, Any]], limit: int = 12) -> list[str]:
    recoveries: list[str] = []
    for lap in laps:
        distance = miles(lap)
        moving_time = int(lap.get("moving_time") or 0)
        pace = _seconds_per_mile(distance, moving_time)
        if pace is None:
            continue
        if moving_time >= 45 and distance <= 0.2 and pace >= 9 * 60:
            recoveries.append(
                f"lap {lap.get('lap_index') or lap.get('split')}: "
                f"{_duration(moving_time)} over {distance:.2f} mi, "
                f"avg HR {_heart_rate(lap.get('average_heartrate'))}"
            )
        if len(recoveries) >= limit:
            break
    return recoveries


def _seconds_per_mile(distance_miles: float, moving_time_seconds: int) -> int | None:
    if distance_miles <= 0 or moving_time_seconds <= 0:
        return None
    return int(moving_time_seconds / distance_miles)


def _feet(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value * 3.28084:.0f} ft"
    return "-"


def _heart_rate(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value:.0f} bpm"
    return "-"


def _cadence(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f} spm"
    return "-"


def _friendly_date(value: str | None) -> str:
    if not value:
        return "unknown date"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%A, %b %-d")
