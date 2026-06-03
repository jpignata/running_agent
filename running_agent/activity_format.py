from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from .workout_classifier import workout_classification_context

METERS_PER_MILE = 1609.344
NUMERIC_TYPES = (int, float)
COMMON_REP_DISTANCES_MILES = (
    300 / METERS_PER_MILE,
    400 / METERS_PER_MILE,
    600 / METERS_PER_MILE,
    800 / METERS_PER_MILE,
    1000 / METERS_PER_MILE,
    1200 / METERS_PER_MILE,
    1600 / METERS_PER_MILE,
    1.0,
    1.5,
)


def miles(activity: dict[str, Any]) -> float:
    return float(activity.get("distance") or 0) / METERS_PER_MILE


def activity_headline(activity: dict[str, Any]) -> str:
    name = activity.get("name") or "Run"
    distance = miles(activity)
    moving_time = int(activity.get("moving_time") or activity.get("elapsed_time") or 0)
    pace = _pace_per_mile(distance, moving_time)
    date = _friendly_date(activity.get("start_date_local") or activity.get("start_date"))
    hr = activity.get("average_heartrate")
    hr_note = f", avg HR {hr:.0f}" if isinstance(hr, NUMERIC_TYPES) else ""
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


def _short_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    return _duration(seconds)


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
    if isinstance(high, NUMERIC_TYPES) and isinstance(low, NUMERIC_TYPES):
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
    rep_lines = _quality_rep_groups(laps)
    short_fast_lines = _short_fast_groups(laps)
    recovery_lines = _recovery_groups(laps)

    if rep_lines:
        lines.append("- Quality-looking reps: " + "; ".join(rep_lines))
    if short_fast_lines:
        lines.append("- Short fast reps: " + "; ".join(short_fast_lines))
    if recovery_lines:
        lines.append("- Recovery-looking segments: " + "; ".join(recovery_lines))
    if len(lines) == 1:
        return []
    return lines


def _quality_rep_groups(laps: list[dict[str, Any]], limit: int = 12) -> list[str]:
    groups: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for lap in laps:
        distance = miles(lap)
        moving_time = int(lap.get("moving_time") or 0)
        pace = _seconds_per_mile(distance, moving_time)
        if pace is None:
            continue
        if 0.18 <= distance <= 1.6 and pace <= 7 * 60:
            groups[_rep_distance_bucket(distance)].append(lap)
    return [
        _format_quality_group(distance, reps[:limit])
        for distance, reps in sorted(groups.items(), reverse=True)
    ]


def _recovery_groups(laps: list[dict[str, Any]], limit: int = 12) -> list[str]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for lap in laps:
        distance = miles(lap)
        moving_time = int(lap.get("moving_time") or 0)
        pace = _seconds_per_mile(distance, moving_time)
        if pace is None:
            continue
        if moving_time >= 45 and distance <= 0.2 and pace >= 9 * 60:
            groups[_round_to_nearest(moving_time, 15)].append(lap)
    return [
        _format_recovery_group(seconds, recoveries[:limit])
        for seconds, recoveries in sorted(groups.items(), reverse=True)
    ]


def _short_fast_groups(laps: list[dict[str, Any]], limit: int = 12) -> list[str]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, lap in enumerate(laps):
        distance = miles(lap)
        moving_time = int(lap.get("moving_time") or 0)
        pace = _seconds_per_mile(distance, moving_time)
        if pace is None:
            continue
        if not (10 <= moving_time <= 35 and 0.03 <= distance <= 0.12 and pace <= 7 * 60):
            continue
        if not (_is_short_recovery(laps[index - 1]) if index > 0 else False) and not (
            _is_short_recovery(laps[index + 1]) if index + 1 < len(laps) else False
        ):
            continue
        groups[_round_to_nearest(moving_time, 5)].append(lap)
    return [
        _format_short_fast_group(seconds, reps[:limit]) for seconds, reps in sorted(groups.items())
    ]


def _format_quality_group(distance: float, reps: list[dict[str, Any]]) -> str:
    lap_numbers = ", ".join(str(rep.get("lap_index") or rep.get("split") or "?") for rep in reps)
    paces = ", ".join(_pace_per_mile(miles(rep), int(rep.get("moving_time") or 0)) for rep in reps)
    heart_rates = [rep.get("average_heartrate") for rep in reps if rep.get("average_heartrate")]
    hr_note = f", avg HRs {', '.join(_heart_rate(hr) for hr in heart_rates)}" if heart_rates else ""
    return f"{len(reps)} x {distance:.2f} mi (laps {lap_numbers}) at {paces}{hr_note}"


def _format_recovery_group(seconds: int, recoveries: list[dict[str, Any]]) -> str:
    lap_numbers = ", ".join(
        str(rep.get("lap_index") or rep.get("split") or "?") for rep in recoveries
    )
    distances = ", ".join(f"{miles(rep):.2f} mi" for rep in recoveries)
    heart_rates = [
        rep.get("average_heartrate") for rep in recoveries if rep.get("average_heartrate")
    ]
    hr_note = f", avg HRs {', '.join(_heart_rate(hr) for hr in heart_rates)}" if heart_rates else ""
    return f"{len(recoveries)} x {_duration(seconds)} recoveries (laps {lap_numbers}) over {distances}{hr_note}"


def _format_short_fast_group(seconds: int, reps: list[dict[str, Any]]) -> str:
    lap_numbers = ", ".join(str(rep.get("lap_index") or rep.get("split") or "?") for rep in reps)
    paces = ", ".join(_pace_per_mile(miles(rep), int(rep.get("moving_time") or 0)) for rep in reps)
    distances = ", ".join(f"{miles(rep):.2f} mi" for rep in reps)
    total_distance = sum(miles(rep) for rep in reps)
    total_moving_time = sum(int(rep.get("moving_time") or 0) for rep in reps)
    average_pace = _pace_per_mile(total_distance, total_moving_time)
    return (
        f"{len(reps)} x {_short_duration(seconds)} "
        f"(laps {lap_numbers}) at {paces}; avg {average_pace}; distances {distances}"
    )


def _rep_distance_bucket(distance_miles: float) -> float:
    for common_distance in COMMON_REP_DISTANCES_MILES:
        if abs(distance_miles - common_distance) <= max(0.03, common_distance * 0.03):
            return round(common_distance, 2)
    return round(distance_miles, 2)


def _round_to_nearest(value: int, increment: int) -> int:
    return int(round(value / increment) * increment)


def _seconds_per_mile(distance_miles: float, moving_time_seconds: int) -> int | None:
    if distance_miles <= 0 or moving_time_seconds <= 0:
        return None
    return int(moving_time_seconds / distance_miles)


def _is_short_recovery(lap: dict[str, Any]) -> bool:
    distance = miles(lap)
    moving_time = int(lap.get("moving_time") or 0)
    pace = _seconds_per_mile(distance, moving_time)
    return bool(
        pace is not None and 30 <= moving_time <= 75 and distance <= 0.12 and pace >= 7 * 60
    )


def _feet(value: Any) -> str:
    if isinstance(value, NUMERIC_TYPES):
        return f"{value * 3.28084:.0f} ft"
    return "-"


def _heart_rate(value: Any) -> str:
    if isinstance(value, NUMERIC_TYPES):
        return f"{value:.0f} bpm"
    return "-"


def _cadence(value: Any) -> str:
    if isinstance(value, NUMERIC_TYPES):
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
