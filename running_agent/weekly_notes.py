from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .coach_time import coach_today
from .storage import append_jsonl, read_jsonl
from .storage_paths import WEEKLY_NOTES_PATH


def append_weekly_note(
    note: str,
    *,
    week_start: date | None = None,
    path: Path = WEEKLY_NOTES_PATH,
) -> dict[str, Any]:
    cleaned = note.strip()
    if not cleaned:
        raise RuntimeError("Weekly note text cannot be empty.")
    target_week_start = week_start or _week_start(coach_today())
    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "week_start": target_week_start.isoformat(),
        "note": cleaned,
    }
    append_jsonl(path, entry)
    return entry


def weekly_notes_for_week(
    week_start: date,
    *,
    path: Path = WEEKLY_NOTES_PATH,
) -> list[dict[str, Any]]:
    target = week_start.isoformat()
    return [
        entry
        for entry in read_jsonl(path)
        if entry.get("week_start") == target and str(entry.get("note") or "").strip()
    ]


def weekly_notes_context(
    week_start: date,
    *,
    path: Path = WEEKLY_NOTES_PATH,
    limit: int = 8,
) -> str:
    notes = weekly_notes_for_week(week_start, path=path)
    if not notes:
        return "No athlete notes were saved for the reviewed week."
    lines = ["Athlete notes for reviewed week:"]
    for entry in notes[-limit:]:
        created_at = str(entry.get("created_at") or "unknown time")
        lines.append(f"- {created_at}: {entry.get('note', '')}")
    return "\n".join(lines)


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())
