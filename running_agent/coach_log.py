from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .activity_format import activity_headline
from .coach_time import coach_today
from .plan_store import planned_workout_for_date
from .storage_paths import COACH_LOG_PATH, prepare_parent


def append_run_result(
    activity: dict[str, Any],
    path: Path = COACH_LOG_PATH,
) -> dict[str, Any]:
    run_date = _activity_date(activity)
    planned = planned_workout_for_date(run_date)
    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": "run_completed",
        "activity_id": activity.get("id"),
        "run_date": run_date.isoformat(),
        "planned_workout": planned or "No matching planned workout found.",
        "completed_run": activity_headline(activity),
    }
    append_coach_log(entry, path=path)
    return entry


def append_coach_log(entry: dict[str, Any], path: Path = COACH_LOG_PATH) -> None:
    prepare_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    path.chmod(0o600)


def append_week_review(
    week_start: str,
    week_end: str,
    summary: str,
    path: Path = COACH_LOG_PATH,
) -> dict[str, Any]:
    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": "week_reviewed",
        "week_start": week_start,
        "week_end": week_end,
        "summary": summary.strip(),
    }
    append_coach_log(entry, path=path)
    return entry


def read_coach_log(path: Path = COACH_LOG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def coach_log_context(path: Path = COACH_LOG_PATH, limit: int = 8) -> str:
    entries = read_coach_log(path)
    if not entries:
        return "No coach log entries have been recorded yet."

    lines = ["Recent coach log:"]
    for entry in entries[-limit:]:
        if entry.get("type") == "run_completed":
            lines.append(
                "- "
                f"{entry.get('run_date', 'unknown date')}: "
                f"planned: {entry.get('planned_workout', '-')}; "
                f"completed: {entry.get('completed_run', '-')}"
            )
        elif entry.get("type") == "week_reviewed":
            lines.append(
                "- "
                f"week {entry.get('week_start', '?')} to {entry.get('week_end', '?')}: "
                f"{entry.get('summary', '')}"
            )
        else:
            lines.append(
                "- "
                f"{entry.get('created_at', 'unknown time')}: "
                f"{entry.get('type', 'note')}: {entry.get('text', '')}"
            )
    return "\n".join(lines)


def _activity_date(activity: dict[str, Any]):
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return coach_today()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return coach_today()
