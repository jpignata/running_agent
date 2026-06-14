from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .storage import read_json_file, write_json_file
from .storage_paths import WEEKLY_PLAN_PATH
from .time_format import human_datetime

PLAN_PATH = WEEKLY_PLAN_PATH
WEEKDAYS = {
    "mon": "Monday",
    "monday": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "tuesday": "Tuesday",
    "wed": "Wednesday",
    "weds": "Wednesday",
    "wednesday": "Wednesday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "thursday": "Thursday",
    "fri": "Friday",
    "friday": "Friday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "sun": "Sunday",
    "sunday": "Sunday",
}
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def save_weekly_plan(
    plan_text: str,
    path: Path = PLAN_PATH,
    week_start: str | date | None = None,
) -> dict[str, Any]:
    plan_text = plan_text.strip()
    if not plan_text:
        raise RuntimeError("Weekly plan text cannot be empty.")

    plan = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "text": plan_text,
    }
    normalized_week_start = _normalize_week_start(week_start)
    if normalized_week_start:
        plan["week_start"] = normalized_week_start
    write_json_file(path, plan)
    return plan


def update_weekly_plan_days(
    updates: dict[str, str],
    path: Path = PLAN_PATH,
) -> dict[str, Any]:
    normalized = _normalize_plan_updates(updates)
    if not normalized:
        raise RuntimeError("At least one weekly plan day update is required.")

    existing = load_weekly_plan(path)
    current_text = (existing or {}).get("text", "").strip() if existing else ""
    parsed = parse_weekly_plan(current_text)
    parsed.update(normalized)
    plan_lines = [
        f"{weekday} {parsed[weekday]}"
        for weekday in WEEKDAY_NAMES
        if weekday in parsed and parsed[weekday].strip()
    ]
    return save_weekly_plan(
        "\n".join(plan_lines),
        path=path,
        week_start=(existing or {}).get("week_start") if existing else None,
    )


def load_weekly_plan(path: Path = PLAN_PATH) -> dict[str, Any] | None:
    return read_json_file(path, default=None)


def weekly_plan_context(path: Path = PLAN_PATH) -> str:
    plan = load_weekly_plan(path)
    if not plan:
        return "No weekly plan has been provided."
    updated_at = human_datetime(plan.get("updated_at"))
    text = plan.get("text", "").strip()
    if not text:
        return "No weekly plan has been provided."
    week_start = plan.get("week_start")
    if week_start:
        return f"Weekly plan for week starting {week_start}, last updated {updated_at}:\n{text}"
    return f"Weekly plan, last updated {updated_at}:\n{text}"


def weekly_plan_context_for_week(target_week_start: date, path: Path = PLAN_PATH) -> str:
    plan = load_weekly_plan(path)
    if not plan:
        return "No saved weekly plan for the target week."
    text = plan.get("text", "").strip()
    if not text:
        return "No saved weekly plan for the target week."
    week_start = plan.get("week_start")
    if week_start != target_week_start.isoformat():
        return (
            f"No saved weekly plan explicitly applies to week starting "
            f"{target_week_start.isoformat()}."
        )
    updated_at = human_datetime(plan.get("updated_at"))
    return (
        f"Saved weekly plan for target week starting {target_week_start.isoformat()}, "
        f"last updated {updated_at}:\n{text}"
    )


def weekly_plan_context_for_date(target_date: date, path: Path = PLAN_PATH) -> str:
    plan = load_weekly_plan(path)
    if not plan:
        return "No weekly plan has been provided."
    updated_at = human_datetime(plan.get("updated_at"))
    text = plan.get("text", "").strip()
    if not text:
        return "No weekly plan has been provided."

    parsed = parse_weekly_plan(text)
    weekday = target_date.strftime("%A")
    matched = parsed.get(weekday)
    if not matched:
        return (
            f"Weekly plan, last updated {updated_at}.\n"
            f"Run date: {target_date.strftime('%A, %b %-d')}.\n"
            f"Matched plan day: none found for {weekday}.\n"
            f"Full weekly plan:\n{text}"
        )
    return (
        f"Weekly plan, last updated {updated_at}.\n"
        f"Run date: {target_date.strftime('%A, %b %-d')}.\n"
        f"Matched plan day: {weekday}.\n"
        f"Planned workout for {weekday}: {matched}\n"
        f"Full weekly plan:\n{text}"
    )


def upcoming_plan_context_after_date(
    target_date: date,
    path: Path = PLAN_PATH,
) -> str:
    plan = load_weekly_plan(path)
    if not plan:
        return "No upcoming plan context available."
    text = plan.get("text", "").strip()
    if not text:
        return "No upcoming plan context available."

    parsed = parse_weekly_plan(text)
    upcoming = []
    week_end = target_date + timedelta(days=6 - target_date.weekday())
    cursor = target_date + timedelta(days=1)
    while cursor <= week_end:
        weekday = cursor.strftime("%A")
        workout = parsed.get(weekday)
        if workout:
            upcoming.append(f"{weekday}: {workout}")
        cursor += timedelta(days=1)

    if not upcoming:
        return f"No planned workouts after {target_date.strftime('%A, %b %-d')} this week."
    return f"Remaining plan after {target_date.strftime('%A, %b %-d')}:\n" + "\n".join(upcoming)


def planned_workout_for_date(target_date: date, path: Path = PLAN_PATH) -> str | None:
    plan = load_weekly_plan(path)
    if not plan:
        return None
    text = plan.get("text", "").strip()
    if not text:
        return None
    return parse_weekly_plan(text).get(target_date.strftime("%A"))


def parse_weekly_plan(plan_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in plan_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z]+)\b[,:-]?\s*(.*)$", line)
        if not match:
            continue
        weekday = WEEKDAYS.get(match.group(1).lower())
        workout = match.group(2).strip(" \t,:-")
        if weekday and workout:
            parsed[weekday] = workout
    return parsed


def _normalize_plan_updates(updates: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_day, raw_workout in updates.items():
        weekday = WEEKDAYS.get(str(raw_day).strip().lower())
        workout = str(raw_workout).strip(" \t,:-")
        if weekday and workout:
            normalized[weekday] = workout
    return normalized


def _normalize_week_start(value: str | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        parsed = date.fromisoformat(stripped)
    except ValueError:
        return None
    return parsed.isoformat()
