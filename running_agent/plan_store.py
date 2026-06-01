from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .storage_paths import WEEKLY_PLAN_PATH, prepare_parent
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


def save_weekly_plan(plan_text: str, path: Path = PLAN_PATH) -> dict[str, Any]:
    plan_text = plan_text.strip()
    if not plan_text:
        raise RuntimeError("Weekly plan text cannot be empty.")

    plan = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "text": plan_text,
    }
    prepare_parent(path)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return plan


def load_weekly_plan(path: Path = PLAN_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def weekly_plan_context(path: Path = PLAN_PATH) -> str:
    plan = load_weekly_plan(path)
    if not plan:
        return "No weekly plan has been provided."
    updated_at = human_datetime(plan.get("updated_at"))
    text = plan.get("text", "").strip()
    if not text:
        return "No weekly plan has been provided."
    return f"Weekly plan, last updated {updated_at}:\n{text}"


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
