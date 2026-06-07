from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable

from .activity_format import recent_runs_context
from .coach_log import coach_log_context
from .coach_time import in_coach_time
from .feedback import summarize_training
from .garmin_context import garmin_readiness_context
from .goal_store import training_goal_context
from .openai_client import coaching_reply
from .plan_store import upcoming_plan_context_after_date, weekly_plan_context_for_date
from .strava_client import StravaClient

EVENING_REPORT_TIME = time(20, 30)
EVENING_REPORT_STATE_KEY = "last_evening_report_date"


def end_of_day_report(
    client: StravaClient,
    target_date: date,
    lookback_days: int = 7,
    garmin_context_provider: Callable[[], str] | None = None,
) -> str:
    activities = _activities_on_or_before(
        client.recent_activities(days=lookback_days),
        target_date=target_date,
    )
    report_date_runs = client.runs_on_date(target_date, search_days=3)
    report_date_context = (
        recent_runs_context(report_date_runs, limit=5)
        if report_date_runs
        else f"No Strava runs completed on {target_date.isoformat()}."
    )
    weekly_plan = weekly_plan_context_for_date(target_date)
    upcoming_plan = upcoming_plan_context_after_date(target_date)
    garmin_context = _current_garmin_context(target_date, garmin_context_provider)
    prompt = (
        f"Write a brief end-of-day running coach text for {target_date.isoformat()} for Telegram. "
        "Recap only that date's exercise briefly, if any; do not mention later activities. Mention "
        "the most useful sleep, recovery, or next-day thing to keep in mind based on Garmin "
        "context, that date's run, the matched plan day, the remaining weekly plan, and the "
        "overall goal. If the remaining plan includes a race, prioritize freshness for that race "
        "and do not invent another key day. Keep it conversational, under 90 words, and do not "
        "use a title, section headers, markdown, or label-style phrases. Write at most two short "
        "paragraphs."
    )
    return coaching_reply(
        prompt,
        training_summary=summarize_training(activities, days=lookback_days),
        recent_runs=report_date_context,
        weekly_plan=f"{weekly_plan}\n\n{upcoming_plan}",
        training_goal=training_goal_context(),
        coach_log=coach_log_context(),
        garmin_context=garmin_context,
        tools_enabled=False,
        max_output_tokens=220,
    )


def should_send_evening_report(now: datetime, state: dict[str, Any]) -> bool:
    now = in_coach_time(now)
    if now.weekday() == 6:
        return False
    if now.time() < EVENING_REPORT_TIME:
        return False
    return state.get(EVENING_REPORT_STATE_KEY) != now.date().isoformat()


def mark_evening_report_sent(now: datetime, state: dict[str, Any]) -> None:
    now = in_coach_time(now)
    state[EVENING_REPORT_STATE_KEY] = now.date().isoformat()


def _current_garmin_context(
    target_date: date,
    provider: Callable[[], str] | None = None,
) -> str:
    try:
        return provider() if provider else garmin_readiness_context(target_date=target_date)
    except RuntimeError as error:
        return f"Garmin readiness context unavailable: {error}"


def _activities_on_or_before(
    activities: list[dict[str, Any]],
    target_date: date,
) -> list[dict[str, Any]]:
    return [
        activity
        for activity in activities
        if (_activity_local_date(activity) is None or _activity_local_date(activity) <= target_date)
    ]


def _activity_local_date(activity: dict[str, Any]) -> date | None:
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
