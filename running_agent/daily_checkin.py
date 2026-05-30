from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable

from .activity_format import recent_runs_context
from .coach_log import coach_log_context
from .feedback import summarize_training
from .garmin_context import garmin_readiness_context
from .goal_store import training_goal_context
from .openai_client import coaching_reply
from .plan_store import planned_workout_for_date, weekly_plan_context_for_date
from .strava_client import StravaClient

DAILY_CHECKIN_TIME = time(5, 30)
DAILY_CHECKIN_STATE_KEY = "last_daily_checkin_date"


def daily_workout_checkin(
    client: StravaClient,
    target_date: date,
    lookback_days: int = 7,
    garmin_context_provider: Callable[[], str] | None = None,
) -> str:
    activities = client.recent_activities(days=lookback_days)
    weekly_plan = weekly_plan_context_for_date(target_date)
    garmin_context = _garmin_context(garmin_context_provider)
    prompt = (
        f"Write a morning workout check-in for {target_date.isoformat()} for Telegram. "
        "Use today's matched plan, this week's recent runs, Garmin readiness context, coach log, "
        "and the overall goal. Tell the athlete what to do in today's workout, how hard to run "
        "it, and anything to watch out for. If Garmin readiness looks poor, suggest a conservative "
        "adjustment. If the plan is missing or ambiguous, say so and give a sensible default. "
        "Keep it concise and practical. Do not claim the plan was saved or changed."
    )

    try:
        note = coaching_reply(
            prompt,
            training_summary=summarize_training(activities, days=lookback_days),
            recent_runs=recent_runs_context(activities, limit=10),
            weekly_plan=weekly_plan,
            training_goal=training_goal_context(),
            coach_log=coach_log_context(),
            garmin_context=garmin_context,
        )
    except RuntimeError as error:
        note = _fallback_daily_checkin(weekly_plan, garmin_context, error)

    return note


def should_send_daily_checkin(now: datetime, state: dict[str, Any]) -> bool:
    if now.time() < DAILY_CHECKIN_TIME:
        return False
    return state.get(DAILY_CHECKIN_STATE_KEY) != now.date().isoformat()


def mark_daily_checkin_sent(now: datetime, state: dict[str, Any]) -> None:
    state[DAILY_CHECKIN_STATE_KEY] = now.date().isoformat()


def has_completed_run_for_date(
    client: StravaClient,
    target_date: date,
    search_days: int = 14,
) -> bool:
    return bool(client.runs_on_date(target_date, search_days=search_days))


def has_planned_workout_for_date(target_date: date) -> bool:
    return planned_workout_for_date(target_date) is not None


def _garmin_context(provider: Callable[[], str] | None) -> str:
    try:
        return provider() if provider else garmin_readiness_context()
    except RuntimeError as error:
        return f"Garmin readiness context unavailable: {error}"


def _fallback_daily_checkin(
    weekly_plan: str,
    garmin_context: str,
    error: RuntimeError,
) -> str:
    return (
        f"AI check-in was unavailable ({error}).\n\n"
        f"{weekly_plan}\n\n"
        f"{garmin_context}\n\n"
        "Basic read: follow the planned workout conservatively. If Garmin readiness, sleep, "
        "or soreness looks poor, keep the run easy or shorten it rather than forcing intensity."
    )
