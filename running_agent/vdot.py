from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .activity_format import METERS_PER_MILE, miles
from .race_results import official_result_for_activity
from .strava_store import load_run_detail

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
    observed_seconds: int
    performance_seconds: int
    source: str
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
            f"{best.name}, {best.race_label} in {_duration(best.performance_seconds)} "
            f"from {best.source} (full activity {best.observed_miles:.2f} mi "
            f"in {_duration(best.observed_seconds)}), VDOT {best.vdot:.1f}. "
            f"Use the nearest published table conservatively: {vdot_training_paces(best.table_vdot)}"
        ),
        "Recent race estimates:",
    ]
    for estimate in estimates[:limit]:
        lines.append(
            "- "
            f"{estimate.name}: {estimate.race_label} in {_duration(estimate.performance_seconds)} "
            f"from {estimate.source}, "
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
    observed_seconds = int(activity.get("moving_time") or activity.get("elapsed_time") or 0)
    standard_label, standard_distance, performance_seconds, source = _race_performance(
        activity,
        observed_distance,
        observed_seconds,
    )
    if standard_distance <= 0 or performance_seconds <= 0 or observed_seconds <= 0:
        return None
    vdot = vdot_from_performance(standard_distance, performance_seconds)
    if vdot is None:
        return None
    return RaceVdotEstimate(
        name=str(activity.get("name") or "Race"),
        race_label=standard_label,
        observed_miles=miles(activity),
        observed_seconds=observed_seconds,
        performance_seconds=performance_seconds,
        source=source,
        vdot=vdot,
        table_vdot=_clamp_table_vdot(round(vdot)),
    )


def _race_performance(
    activity: dict[str, Any],
    observed_distance: float,
    observed_seconds: int,
) -> tuple[str, float, int, str]:
    official_result = official_result_for_activity(activity)
    if official_result:
        return (
            str(official_result.get("distance") or "race"),
            float(official_result.get("distance_meters") or 0),
            int(official_result.get("time_seconds") or 0),
            "official saved race result",
        )
    best_effort = _best_standard_effort(activity)
    if best_effort:
        label, distance, seconds = best_effort
        return label, distance, seconds, "Strava best effort"
    label, distance = _standardized_race_distance(observed_distance)
    return label, distance, observed_seconds, "full activity"


def _best_standard_effort(activity: dict[str, Any]) -> tuple[str, float, int] | None:
    detail = _activity_detail(activity)
    best_efforts = detail.get("best_efforts") or activity.get("best_efforts") or []
    if not isinstance(best_efforts, list):
        return None
    standard_by_label = {label.lower(): (label, distance) for label, distance in STANDARD_RACES}
    matches = []
    for effort in best_efforts:
        if not isinstance(effort, dict):
            continue
        name = str(effort.get("name") or "").lower()
        if name not in standard_by_label:
            continue
        seconds = int(effort.get("moving_time") or effort.get("elapsed_time") or 0)
        if seconds <= 0:
            continue
        label, distance = standard_by_label[name]
        matches.append((distance, label, seconds))
    if not matches:
        return None
    distance, label, seconds = max(matches)
    return label, distance, seconds


def _activity_detail(activity: dict[str, Any]) -> dict[str, Any]:
    activity_id = activity.get("id")
    if activity_id is None:
        return activity
    return load_run_detail(activity_id) or activity


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
