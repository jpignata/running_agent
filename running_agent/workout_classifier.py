from __future__ import annotations

import re
from datetime import date
from typing import Any

from .plan_store import planned_workout_for_date

METERS_PER_MILE = 1609.344
RACE_WORDS = ("race", "time trial", " tt", "marathon", "half marathon", "5k", "10k")
STRUCTURED_WORDS = (
    "workout",
    "track",
    "interval",
    "repeat",
    "reps",
    "tempo",
    "threshold",
    "fartlek",
    "progression",
    "strides",
    " wu",
    " cd",
)
EASY_WORDS = ("easy", "recovery", "shakeout")
LONG_WORDS = ("long", "long run")


def workout_classification_context(activity: dict[str, Any], target_date: date) -> str:
    planned = planned_workout_for_date(target_date)
    classification, reason, emphasis = classify_workout(activity, planned)
    lines = [
        "Workout classification:",
        f"- Type: {classification}",
        f"- Primary reason: {reason}",
        f"- Coaching emphasis: {emphasis}",
    ]
    if planned:
        lines.insert(2, f"- Matched planned workout: {planned}")
    return "\n".join(lines)


def classify_workout(
    activity: dict[str, Any], planned: str | None = None
) -> tuple[str, str, str]:
    plan = f" {planned.lower()} " if planned else ""
    quality_count = _quality_lap_count(activity)
    recovery_count = _recovery_lap_count(activity)
    distance = miles(activity)
    moving_time = int(activity.get("moving_time") or 0)

    if _contains_any(plan, RACE_WORDS):
        return (
            "race",
            "matched weekly plan indicates race or time trial intent",
            "focus on race execution, pacing, and recovery rather than workout compliance",
        )

    if _looks_structured_plan(plan):
        return (
            "structured workout",
            "matched weekly plan contains workout structure or quality-session language",
            "compare reps, recoveries, and pacing against the planned workout",
        )

    if _contains_any(plan, LONG_WORDS):
        return (
            "long run",
            "matched weekly plan indicates a long run",
            "focus on endurance, fueling, pacing discipline, and recovery",
        )

    if quality_count >= 2 and recovery_count >= 2:
        return (
            "structured workout",
            f"detected {quality_count} quality-looking laps and {recovery_count} recovery-looking laps",
            "use the lap structure heavily and compare it with the plan if available",
        )

    if distance >= 10 or moving_time >= 90 * 60:
        return (
            "long run",
            "distance or duration is long-run sized",
            "focus on aerobic durability, pacing drift, fueling, and recovery",
        )

    if _contains_any(plan, EASY_WORDS):
        return (
            "easy run",
            "matched weekly plan indicates easy or recovery running",
            "avoid over-analyzing laps; focus on effort control and recovery",
        )

    return (
        "easy run",
        "no race, long-run, or structured workout signal was detected",
        "keep analysis light and focus on consistency, effort, and readiness for the next key run",
    )


def _looks_structured_plan(plan: str) -> bool:
    if _contains_any(plan, STRUCTURED_WORDS):
        return True
    return bool(re.search(r"\b\d+\s*x\s*\d+", plan) or re.search(r"\b\d+x\d+", plan))


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _quality_lap_count(activity: dict[str, Any]) -> int:
    return sum(1 for lap in activity.get("laps", []) if _is_quality_lap(lap))


def _recovery_lap_count(activity: dict[str, Any]) -> int:
    return sum(1 for lap in activity.get("laps", []) if _is_recovery_lap(lap))


def _is_quality_lap(lap: dict[str, Any]) -> bool:
    distance = miles(lap)
    moving_time = int(lap.get("moving_time") or 0)
    pace = _seconds_per_mile(distance, moving_time)
    return bool(pace is not None and 0.18 <= distance <= 1.6 and pace <= 7 * 60)


def _is_recovery_lap(lap: dict[str, Any]) -> bool:
    distance = miles(lap)
    moving_time = int(lap.get("moving_time") or 0)
    pace = _seconds_per_mile(distance, moving_time)
    return bool(
        pace is not None and moving_time >= 45 and distance <= 0.2 and pace >= 9 * 60
    )


def _seconds_per_mile(distance_miles: float, moving_time_seconds: int) -> int | None:
    if distance_miles <= 0 or moving_time_seconds <= 0:
        return None
    return int(moving_time_seconds / distance_miles)


def miles(activity: dict[str, Any]) -> float:
    return float(activity.get("distance") or 0) / METERS_PER_MILE
