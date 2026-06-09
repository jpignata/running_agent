from __future__ import annotations

from datetime import timedelta
from typing import Any

from .activity_format import activity_headline, detailed_activity_context
from .coach_time import coach_today
from .strava_store import activity_local_date, list_run_summaries, load_run_detail

RACE_WORKOUT_TYPE = 1
RACE_NAME_WORDS = ("race", "5k", "10k", "half marathon", "marathon", "mile")
GENERIC_QUERY_WORDS = {
    "activity",
    "from",
    "last",
    "latest",
    "race",
    "races",
    "raced",
    "run",
    "week",
    "workout",
}


def query_local_runs(
    *,
    query: str = "",
    days: int = 365,
    limit: int = 8,
    races_only: bool = False,
) -> str:
    runs = _matching_runs(query=query, days=days, races_only=races_only)
    limit = max(1, min(limit, 20))
    runs = runs[:limit]
    if not runs:
        scope = "race-like synced Strava runs" if races_only else "synced Strava runs"
        return f"No matching {scope} found in the local store for the last {days} days."

    lines = [
        "Matching synced Strava "
        f"{'race-like ' if races_only else ''}runs, newest first, last {days} days:"
    ]
    for activity in runs:
        race_note = " race-like" if _looks_like_race(activity) else ""
        detail_note = (
            " details synced" if load_run_detail(activity["id"]) else " details not synced"
        )
        lines.append(
            f"- id {activity['id']}: {activity_headline(activity)}{race_note}; {detail_note}"
        )
    return "\n".join(lines)


def get_local_run_details(
    *,
    selector: str = "latest_run",
    activity_id: str = "",
    query: str = "",
    date: str = "",
    days: int = 365,
) -> str:
    summary = _select_run(
        selector=selector,
        activity_id=activity_id,
        query=query,
        date=date,
        days=days,
    )
    if not summary:
        return "No matching synced Strava run found in the local store."

    detail = load_run_detail(summary["id"])
    if not detail:
        return (
            f"Found {activity_headline(summary)}, but detailed lap data is not synced locally. "
            f"Run `python -m running_agent sync-strava --days {days}` to backfill details."
        )
    activity_date = activity_local_date(detail) or activity_local_date(summary)
    target_date = activity_date if _is_current_training_week(activity_date) else None
    context = detailed_activity_context(detail, target_date=target_date)
    if activity_date and target_date is None:
        context += (
            "\n\nHistorical plan note: no weekly plan snapshot is stored for this activity date. "
            "Use the lap data and derived workout signals for this run; do not compare it to "
            "the current saved weekly plan."
        )
    return context


def _select_run(
    *,
    selector: str,
    activity_id: str,
    query: str,
    date: str,
    days: int,
) -> dict[str, Any] | None:
    runs = _matching_runs(query=query, days=days, races_only=False)
    if selector == "activity_id" and activity_id:
        return next((run for run in runs if str(run.get("id")) == str(activity_id)), None)
    if selector == "latest_race":
        return next((run for run in runs if _looks_like_race(run)), None)
    if selector == "date" and date:
        return next((run for run in runs if str(activity_local_date(run)) == date), None)
    if selector == "query" and query.strip():
        return runs[0] if runs else None
    return runs[0] if runs else None


def _matching_runs(query: str, days: int, races_only: bool) -> list[dict[str, Any]]:
    days = max(1, min(days, 3650))
    start_date, end_date = _date_window(query, days)
    runs = []
    for activity in list_run_summaries():
        activity_date = activity_local_date(activity)
        if activity.get("id") is None:
            continue
        if activity_date is not None and activity_date < start_date:
            continue
        if end_date is not None and activity_date is not None and activity_date > end_date:
            continue
        runs.append(activity)
    if races_only:
        runs = [activity for activity in runs if _looks_like_race(activity)]
    if query.strip():
        terms = _query_terms(query)
        runs = [activity for activity in runs if _matches_terms(activity, terms)]
    return runs


def _date_window(query: str, days: int):
    today = coach_today()
    if "last week" in query.lower():
        this_week_start = today - timedelta(days=today.weekday())
        last_week_start = this_week_start - timedelta(days=7)
        return last_week_start, this_week_start - timedelta(days=1)
    return today - timedelta(days=days - 1), None


def _is_current_training_week(activity_date) -> bool:
    if activity_date is None:
        return False
    today = coach_today()
    week_start = today - timedelta(days=today.weekday())
    return week_start <= activity_date <= week_start + timedelta(days=6)


def _looks_like_race(activity: dict[str, Any]) -> bool:
    if activity.get("workout_type") == RACE_WORKOUT_TYPE:
        return True
    name = str(activity.get("name") or "").lower()
    return any(word in name for word in RACE_NAME_WORDS)


def _matches_terms(activity: dict[str, Any], terms: list[str]) -> bool:
    if not terms:
        return True
    haystack = " ".join(
        str(value or "").lower()
        for value in [
            activity.get("name"),
            activity.get("start_date_local"),
            activity.get("start_date"),
        ]
    )
    return all(term in haystack for term in terms)


def _query_terms(query: str) -> list[str]:
    return [
        term.lower()
        for term in query.split()
        if term.strip() and term.lower() not in GENERIC_QUERY_WORDS
    ]
