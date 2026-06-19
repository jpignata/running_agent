from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .activity_format import miles
from .coach_log import read_coach_log
from .coach_time import coach_today
from .heart_rate import heart_rate_percent, observed_max_heart_rate
from .plan_store import planned_workout_for_date
from .post_run_feedback import read_post_run_feedback
from .storage import read_json_file, write_json_file
from .storage_paths import (
    COACH_LOG_PATH,
    RUN_FEEDBACK_PATH,
    RUN_MEMORY_PATH,
    STRAVA_ACTIVITIES_PATH,
    STRAVA_DETAILS_DIR,
)
from .strava_store import activity_local_date, list_run_summaries, load_run_detail
from .workout_classifier import classify_workout


def refresh_run_memory(
    *,
    days: int = 28,
    today: date | None = None,
    output_path: Path = RUN_MEMORY_PATH,
    summaries_path: Path = STRAVA_ACTIVITIES_PATH,
    details_dir: Path = STRAVA_DETAILS_DIR,
    feedback_path: Path = RUN_FEEDBACK_PATH,
    coach_log_path: Path = COACH_LOG_PATH,
) -> dict[str, Any]:
    today = today or coach_today()
    records = build_run_memory(
        days=days,
        today=today,
        summaries_path=summaries_path,
        details_dir=details_dir,
        feedback_path=feedback_path,
        coach_log_path=coach_log_path,
    )
    data = {
        "generated_for": today.isoformat(),
        "lookback_days": days,
        "runs": records,
    }
    write_json_file(output_path, data, trailing_newline=True)
    return data


def validate_run_memory(
    *,
    records: list[dict[str, Any]] | None = None,
    memory_path: Path = RUN_MEMORY_PATH,
    feedback_path: Path = RUN_FEEDBACK_PATH,
) -> dict[str, Any]:
    """Check that the derived run-memory index reflects source feedback entries."""
    if records is None:
        data = load_run_memory(memory_path)
        loaded = data.get("runs")
        records = loaded if isinstance(loaded, list) else []

    feedback_entries = read_post_run_feedback(feedback_path)
    missing_feedback: list[dict[str, Any]] = []
    stale_feedback: list[dict[str, Any]] = []
    record_indexes = _record_feedback_indexes(records)

    for entry in feedback_entries:
        matches = _matching_memory_records(entry, record_indexes)
        if not matches:
            missing_feedback.append(_feedback_identity(entry))
            continue
        if not any(_record_contains_feedback(record, entry) for record in matches):
            stale_feedback.append(_feedback_identity(entry))

    ok = not missing_feedback and not stale_feedback
    return {
        "ok": ok,
        "feedback_entries": len(feedback_entries),
        "run_records": len(records),
        "missing_feedback": missing_feedback,
        "stale_feedback": stale_feedback,
    }


def load_run_memory(path: Path = RUN_MEMORY_PATH) -> dict[str, Any]:
    data = read_json_file(path, default={}, suppress_errors=True)
    return data if isinstance(data, dict) else {}


def build_run_memory(
    *,
    days: int = 28,
    today: date | None = None,
    summaries_path: Path = STRAVA_ACTIVITIES_PATH,
    details_dir: Path = STRAVA_DETAILS_DIR,
    feedback_path: Path = RUN_FEEDBACK_PATH,
    coach_log_path: Path = COACH_LOG_PATH,
) -> list[dict[str, Any]]:
    today = today or coach_today()
    start_date = today - timedelta(days=max(1, days) - 1)
    feedback_by_id, feedback_by_date = _feedback_indexes(read_post_run_feedback(feedback_path))
    log_by_id, log_by_date = _coach_log_indexes(read_coach_log(coach_log_path))

    summaries = list_run_summaries(summaries_path)
    max_heart_rate = observed_max_heart_rate(summaries)

    records: list[dict[str, Any]] = []
    for summary in reversed(summaries):
        run_date = activity_local_date(summary)
        if run_date is None or not start_date <= run_date <= today:
            continue
        activity_id = summary.get("id")
        detail = load_run_detail(activity_id, details_dir) if activity_id is not None else None
        activity = _merge_activity(summary, detail)
        planned = _planned_workout(activity_id, run_date, log_by_id, log_by_date)
        classification, reason, emphasis = classify_workout(activity, planned)
        feedback = _matching_feedback(activity_id, run_date, feedback_by_id, feedback_by_date)
        record = {
            "activity_id": activity_id,
            "date": run_date.isoformat(),
            "name": activity.get("name") or "Run",
            "distance_miles": round(miles(activity), 2),
            "moving_time_seconds": int(
                activity.get("moving_time") or activity.get("elapsed_time") or 0
            ),
            "pace_per_mile": _pace_per_mile(miles(activity), activity),
            "average_heartrate": activity.get("average_heartrate"),
            "planned_workout": planned,
            "classification": classification,
            "classification_reason": reason,
            "coaching_emphasis": emphasis,
            "lap_count": len(activity.get("laps") or []),
            "feedback": feedback,
            "tags": _tags(classification, planned, feedback),
        }
        avg_hr_percent = heart_rate_percent(activity.get("average_heartrate"), max_heart_rate)
        if avg_hr_percent is not None:
            record["average_heartrate_percent_max"] = avg_hr_percent
            record["observed_max_heartrate"] = max_heart_rate
        records.append(record)
    return records


def run_memory_context(records: list[dict[str, Any]] | None = None, *, limit: int = 12) -> str:
    if records is None:
        data = load_run_memory()
        loaded = data.get("runs")
        records = loaded if isinstance(loaded, list) else []
    if not records:
        return "No run memory records have been built yet."

    lines = [f"Run memory, latest {min(limit, len(records))} of {len(records)} runs:"]
    for record in records[-limit:]:
        parts = [
            str(record.get("date") or "?"),
            str(record.get("name") or "Run"),
            f"{float(record.get('distance_miles') or 0):.2f} mi",
            str(record.get("classification") or "run"),
        ]
        feedback = record.get("feedback") or []
        if feedback:
            latest = feedback[-1]
            subjective = []
            if latest.get("rpe") is not None:
                subjective.append(f"RPE {latest['rpe']}")
            if latest.get("legs"):
                subjective.append(f"legs {latest['legs']}")
            if latest.get("pain"):
                subjective.append(f"pain {latest['pain']}")
            if subjective:
                parts.append(", ".join(subjective))
        hr = record.get("average_heartrate")
        hr_percent = record.get("average_heartrate_percent_max")
        if hr is not None and hr_percent is not None:
            parts.append(f"avg HR {float(hr):.0f} bpm / {hr_percent}% max HR")
        tags = record.get("tags") or []
        if tags:
            parts.append("tags " + ", ".join(tags))
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


def _merge_activity(summary: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(detail, dict):
        return dict(summary)
    return {**summary, **detail}


def _pace_per_mile(distance_miles: float, activity: dict[str, Any]) -> str:
    moving_time = int(activity.get("moving_time") or activity.get("elapsed_time") or 0)
    if distance_miles <= 0 or moving_time <= 0:
        return "unknown"
    seconds_per_mile = int(moving_time / distance_miles)
    minutes, seconds = divmod(seconds_per_mile, 60)
    return f"{minutes}:{seconds:02d}/mi"


def _feedback_indexes(
    entries: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    by_date: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        activity_id = entry.get("activity_id")
        if activity_id is not None:
            by_id.setdefault(str(activity_id), []).append(entry)
        run_date = entry.get("run_date")
        if isinstance(run_date, str):
            by_date.setdefault(run_date, []).append(entry)
    return by_id, by_date


def _record_feedback_indexes(
    records: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    by_date: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        activity_id = record.get("activity_id")
        if activity_id is not None:
            by_id.setdefault(str(activity_id), []).append(record)
        run_date = record.get("date")
        if isinstance(run_date, str):
            by_date.setdefault(run_date, []).append(record)
    return by_id, by_date


def _matching_memory_records(
    entry: dict[str, Any],
    indexes: tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    by_id, by_date = indexes
    activity_id = entry.get("activity_id")
    if activity_id is not None and str(activity_id) in by_id:
        return by_id[str(activity_id)]
    run_date = entry.get("run_date")
    if isinstance(run_date, str):
        return by_date.get(run_date, [])
    return []


def _record_contains_feedback(record: dict[str, Any], entry: dict[str, Any]) -> bool:
    expected = _feedback_public_fields(entry)
    for feedback in record.get("feedback") or []:
        if all(feedback.get(key) == value for key, value in expected.items()):
            return True
    return False


def _feedback_identity(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: entry[key] for key in ("activity_id", "run_date", "created_at", "raw") if key in entry
    }


def _coach_log_indexes(
    entries: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_date: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("type") != "run_completed":
            continue
        activity_id = entry.get("activity_id")
        if activity_id is not None:
            by_id[str(activity_id)] = entry
        run_date = entry.get("run_date")
        if isinstance(run_date, str):
            by_date[run_date] = entry
    return by_id, by_date


def _planned_workout(
    activity_id: Any,
    run_date: date,
    log_by_id: dict[str, dict[str, Any]],
    log_by_date: dict[str, dict[str, Any]],
) -> str | None:
    entry = log_by_id.get(str(activity_id)) if activity_id is not None else None
    if entry is None:
        entry = log_by_date.get(run_date.isoformat())
    if entry:
        planned = entry.get("planned_workout")
        if isinstance(planned, str) and planned != "No matching planned workout found.":
            return planned
    return planned_workout_for_date(run_date)


def _matching_feedback(
    activity_id: Any,
    run_date: date,
    feedback_by_id: dict[str, list[dict[str, Any]]],
    feedback_by_date: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if activity_id is not None and str(activity_id) in feedback_by_id:
        return [_feedback_public_fields(entry) for entry in feedback_by_id[str(activity_id)]]
    return [
        _feedback_public_fields(entry) for entry in feedback_by_date.get(run_date.isoformat(), [])
    ]


def _feedback_public_fields(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: entry[key]
        for key in ("created_at", "raw", "rpe", "legs", "pain", "notes")
        if key in entry
    }


def _tags(classification: str, planned: str | None, feedback: list[dict[str, Any]]) -> list[str]:
    tags = {classification.replace(" ", "_")}
    plan = (planned or "").lower()
    if "race" in plan:
        tags.add("planned_race")
    if feedback:
        latest = feedback[-1]
        rpe = latest.get("rpe")
        if isinstance(rpe, int) and rpe >= 8:
            tags.add("high_rpe")
        if isinstance(rpe, int) and rpe <= 4:
            tags.add("low_rpe")
        pain = str(latest.get("pain") or "").lower()
        if pain and pain not in {"no", "none"}:
            tags.add("pain_or_soreness")
        legs = str(latest.get("legs") or "").lower()
        if legs in {"heavy", "dead", "sore", "tired"}:
            tags.add("leg_fatigue")
    return sorted(tags)
