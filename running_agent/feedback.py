from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any

METERS_PER_MILE = 1609.344


def summarize_training(activities: list[dict[str, Any]], days: int) -> str:
    runs = [activity for activity in activities if activity.get("type") == "Run"]
    if not runs:
        return f"No runs found in the last {days} days."

    total_miles = sum(_miles(run) for run in runs)
    longest = max(runs, key=_miles)
    weekly = _weekly_mileage(runs)
    average_run = total_miles / len(runs)
    hr_values = [run["average_heartrate"] for run in runs if run.get("average_heartrate")]

    lines = [
        f"Reviewed {len(runs)} runs over the last {days} days.",
        f"Total volume: {total_miles:.1f} mi, averaging {average_run:.1f} mi per run.",
        f"Longest run: {_miles(longest):.1f} mi on {longest.get('start_date_local', 'unknown date')}.",
    ]

    if weekly:
        week_notes = ", ".join(f"{week}: {miles:.1f} mi" for week, miles in sorted(weekly.items()))
        lines.append(f"Weekly mileage: {week_notes}.")

    if hr_values:
        lines.append(f"Average HR across HR-tagged runs: {mean(hr_values):.0f} bpm.")
    else:
        lines.append("No heart-rate data found, so effort feedback is limited for now.")

    lines.extend(_training_notes(runs, total_miles, longest_miles=_miles(longest), days=days))
    return "\n".join(lines)


def _training_notes(
    runs: list[dict[str, Any]], total_miles: float, longest_miles: float, days: int
) -> list[str]:
    notes: list[str] = []
    weekly_equivalent = total_miles * (7 / days)

    if weekly_equivalent < 20:
        notes.append(
            "Feedback: your current volume is light for marathon prep; build gradually before "
            "asking the long run to carry too much of the load."
        )
    elif weekly_equivalent < 35:
        notes.append(
            "Feedback: this is a workable base-building range; consistency and easy mileage "
            "matter more than flashy workouts right now."
        )
    else:
        notes.append(
            "Feedback: you have meaningful marathon volume; watch recovery and keep most runs easy."
        )

    if longest_miles > 0 and longest_miles / max(total_miles, 1) > 0.45:
        notes.append(
            "Watch-out: the long run is a large share of this window's mileage. That can raise "
            "injury risk if weekday volume is sparse."
        )

    if len(runs) < max(3, days // 7 * 3):
        notes.append("Consistency note: add frequency before adding intensity.")

    return notes


def _miles(activity: dict[str, Any]) -> float:
    return float(activity.get("distance") or 0) / METERS_PER_MILE


def _weekly_mileage(runs: list[dict[str, Any]]) -> dict[str, float]:
    weekly = defaultdict(float)
    for run in runs:
        start = run.get("start_date_local")
        if not start:
            continue
        week = datetime.fromisoformat(start.replace("Z", "+00:00")).strftime("%G-W%V")
        weekly[week] += _miles(run)
    return dict(weekly)
