from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .activity_format import METERS_PER_MILE, miles

RACE_WORKOUT_TYPE = 1
STANDARD_RACES = (
    ("1 mile", 1609.344),
    ("5K", 5000.0),
    ("10K", 10000.0),
    ("Half marathon", 21097.5),
    ("Marathon", 42195.0),
)
STANDARD_DISTANCE_TOLERANCE = 0.03
RACE_NAME_WORDS = ("race", "5k", "10k", "half marathon", "marathon", "mile")

VDOT_PACE_TABLE = {
    45: ("9:00-9:53/mi", "7:59/mi", "7:31/mi", "6:55/mi", "6:20/mi"),
    46: ("8:52-9:45/mi", "7:51/mi", "7:24/mi", "6:49/mi", "6:15/mi"),
    47: ("8:44-9:36/mi", "7:43/mi", "7:17/mi", "6:42/mi", "6:09/mi"),
    48: ("8:36-9:28/mi", "7:35/mi", "7:10/mi", "6:36/mi", "6:04/mi"),
    49: ("8:24-9:17/mi", "7:26/mi", "7:03/mi", "6:30/mi", "5:59/mi"),
    50: ("8:16-9:06/mi", "7:18/mi", "6:52/mi", "6:18/mi", "5:46/mi"),
    51: ("8:08-8:57/mi", "7:09/mi", "6:44/mi", "6:12/mi", "5:41/mi"),
    52: ("8:00-8:49/mi", "7:02/mi", "6:38/mi", "6:06/mi", "5:36/mi"),
    53: ("7:52-8:40/mi", "6:54/mi", "6:32/mi", "6:00/mi", "5:32/mi"),
    54: ("7:45-8:32/mi", "6:47/mi", "6:26/mi", "5:54/mi", "5:27/mi"),
    55: ("7:37-8:23/mi", "6:40/mi", "6:20/mi", "5:49/mi", "5:23/mi"),
}


@dataclass(frozen=True)
class RaceVdotEstimate:
    name: str
    race_label: str
    observed_miles: float
    seconds: int
    vdot: float
    table_vdot: int


def vdot_from_performance(distance_meters: float, seconds: int) -> float | None:
    if distance_meters <= 0 or seconds <= 0:
        return None
    minutes = seconds / 60
    velocity = distance_meters / minutes
    vo2 = -4.6 + 0.182258 * velocity + 0.000104 * velocity * velocity
    percent_vo2max = (
        0.8 + 0.1894393 * math.exp(-0.012778 * minutes) + 0.2989558 * math.exp(-0.1932605 * minutes)
    )
    return vo2 / percent_vo2max


def vdot_training_paces(table_vdot: int) -> str:
    table_vdot = _clamp_table_vdot(table_vdot)
    easy, marathon, threshold, interval, repetition = VDOT_PACE_TABLE[table_vdot]
    return (
        f"VDOT {table_vdot} paces: Easy {easy}, Marathon {marathon}, "
        f"Threshold {threshold}, Interval {interval}, Repetition {repetition}."
    )


def race_vdot_context(activities: list[dict[str, Any]], limit: int = 3) -> str:
    estimates = race_vdot_estimates(activities)
    if not estimates:
        return "No deterministic race-derived VDOT estimate is available from recent runs."

    best = max(estimates, key=lambda estimate: estimate.vdot)
    lines = [
        "Deterministic race-derived VDOT context:",
        (
            "Best recent race estimate: "
            f"{best.name}, standardized as {best.race_label} in {_duration(best.seconds)} "
            f"(observed {best.observed_miles:.2f} mi), VDOT {best.vdot:.1f}. "
            f"Use the nearest published table conservatively: {vdot_training_paces(best.table_vdot)}"
        ),
        "Recent race estimates:",
    ]
    for estimate in estimates[:limit]:
        lines.append(
            "- "
            f"{estimate.name}: {estimate.race_label} in {_duration(estimate.seconds)}, "
            f"VDOT {estimate.vdot:.1f}, table VDOT {estimate.table_vdot}."
        )
    return "\n".join(lines)


def race_vdot_estimates(activities: list[dict[str, Any]]) -> list[RaceVdotEstimate]:
    estimates: list[RaceVdotEstimate] = []
    for activity in activities:
        estimate = race_vdot_estimate(activity)
        if estimate:
            estimates.append(estimate)
    return estimates


def race_vdot_estimate(activity: dict[str, Any]) -> RaceVdotEstimate | None:
    if activity.get("type") != "Run" or not _looks_like_race(activity):
        return None
    observed_distance = float(activity.get("distance") or 0)
    seconds = int(activity.get("moving_time") or activity.get("elapsed_time") or 0)
    standard_label, standard_distance = _standardized_race_distance(observed_distance)
    if standard_distance <= 0 or seconds <= 0:
        return None
    vdot = vdot_from_performance(standard_distance, seconds)
    if vdot is None:
        return None
    return RaceVdotEstimate(
        name=str(activity.get("name") or "Race"),
        race_label=standard_label,
        observed_miles=miles(activity),
        seconds=seconds,
        vdot=vdot,
        table_vdot=_clamp_table_vdot(round(vdot)),
    )


def _standardized_race_distance(distance_meters: float) -> tuple[str, float]:
    for label, standard_distance in STANDARD_RACES:
        relative_delta = abs(distance_meters - standard_distance) / standard_distance
        if relative_delta <= STANDARD_DISTANCE_TOLERANCE:
            return label, standard_distance
    return (f"{distance_meters / METERS_PER_MILE:.2f} mi", distance_meters)


def _looks_like_race(activity: dict[str, Any]) -> bool:
    if activity.get("workout_type") == RACE_WORKOUT_TYPE:
        return True
    name = str(activity.get("name") or "").lower()
    return any(word in name for word in RACE_NAME_WORDS)


def _clamp_table_vdot(value: int) -> int:
    return min(max(value, min(VDOT_PACE_TABLE)), max(VDOT_PACE_TABLE))


def _duration(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
