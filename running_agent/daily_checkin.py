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
from .plan_store import planned_workout_for_date, weekly_plan_context_for_date
from .strava_client import StravaClient
from .strava_store import list_run_summaries, load_run_detail
from .weather_client import weather_for_location_time, weather_summary

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
    garmin_context = current_garmin_context(garmin_context_provider)
    weather_context = current_weather_context(target_date, activities)
    prompt = (
        f"Write a morning workout check-in for {target_date.isoformat()} for Telegram. "
        "Open conversationally, like a coach texting in the morning. A short greeting such as "
        "'Good morning' or 'Hey' is appropriate. Then state today's planned workout naturally, "
        "for example 'Today you have...' rather than starting with a terse label. "
        "Use today's matched plan, this week's recent runs, Garmin readiness context, weather "
        "context, coach log, and the overall goal. Tell the athlete what to do in today's "
        "workout, how hard to run it, and anything to watch out for. Interpret Garmin readiness "
        "in relation to recent training: low readiness after a hard workout, long run, or race "
        "can be normal. Interpret weather as execution context: heat, humidity, dew point, wind, "
        "or precipitation can justify effort caps, hydration reminders, or slower pace targets. "
        "Do not downgrade the plan based on one Garmin metric or one weather metric alone. "
        "Prefer execution adjustments first, such as easing into the warmup, capping effort, "
        "or adding stop conditions. Recommend changing the workout only when multiple fatigue "
        "signals align with recent training or coach log context. If the plan is missing or "
        "ambiguous, say so and give a sensible default. Keep it concise and practical. Do not "
        "claim the plan was saved or changed."
    )

    return coaching_reply(
        prompt,
        training_summary=summarize_training(activities, days=lookback_days),
        recent_runs=recent_runs_context(activities, limit=10),
        weekly_plan=weekly_plan,
        training_goal=training_goal_context(),
        coach_log=coach_log_context(),
        garmin_context=garmin_context,
        weather_context=weather_context,
        tools_enabled=False,
    )


def should_send_daily_checkin(now: datetime, state: dict[str, Any]) -> bool:
    now = in_coach_time(now)
    if now.time() < DAILY_CHECKIN_TIME:
        return False
    return state.get(DAILY_CHECKIN_STATE_KEY) != now.date().isoformat()


def mark_daily_checkin_sent(now: datetime, state: dict[str, Any]) -> None:
    now = in_coach_time(now)
    state[DAILY_CHECKIN_STATE_KEY] = now.date().isoformat()


def has_completed_run_for_date(
    client: StravaClient,
    target_date: date,
    search_days: int = 14,
) -> bool:
    return bool(client.runs_on_date(target_date, search_days=search_days))


def has_planned_workout_for_date(target_date: date) -> bool:
    return planned_workout_for_date(target_date) is not None


def current_garmin_context(provider: Callable[[], str] | None = None) -> str:
    try:
        return provider() if provider else garmin_readiness_context()
    except RuntimeError as error:
        return f"Garmin readiness context unavailable: {error}"


def current_weather_context(
    target_date: date,
    activities: list[dict[str, Any]] | None = None,
) -> str:
    location = _latest_known_run_location(activities or [])
    if location is None:
        return "Weather context unavailable: no recent Strava start location found."
    latitude, longitude, timezone_name = location
    try:
        weather = weather_for_location_time(
            latitude=latitude,
            longitude=longitude,
            target_date=target_date,
            target_time=DAILY_CHECKIN_TIME,
            timezone_name=timezone_name,
        )
    except RuntimeError as error:
        return f"Weather context unavailable: {error}"
    except Exception as error:
        return f"Weather context unavailable: {error}"
    summary = weather_summary(weather)
    if not summary:
        return "Weather context unavailable: no weather returned for latest run location."
    return (
        "Weather near latest known Strava start location "
        f"at about {DAILY_CHECKIN_TIME.strftime('%-I:%M%p').lower()}: {summary}."
    )


def _latest_known_run_location(
    activities: list[dict[str, Any]],
) -> tuple[float, float, str] | None:
    for activity in activities:
        location = _activity_location(activity)
        if location:
            return location
    for summary in list_run_summaries():
        location = _activity_location(summary)
        if location:
            return location
        activity_id = summary.get("id")
        detail = load_run_detail(activity_id) if activity_id is not None else None
        if detail:
            location = _activity_location(detail)
            if location:
                return location
    return None


def _activity_location(activity: dict[str, Any]) -> tuple[float, float, str] | None:
    if activity.get("type") not in {None, "Run"}:
        return None
    latlng = activity.get("start_latlng")
    if (
        not isinstance(latlng, list)
        or len(latlng) != 2
        or not isinstance(latlng[0], (int, float))
        or not isinstance(latlng[1], (int, float))
    ):
        return None
    timezone_name = _activity_timezone(activity) or "auto"
    return float(latlng[0]), float(latlng[1]), timezone_name


def _activity_timezone(activity: dict[str, Any]) -> str | None:
    timezone_value = activity.get("timezone")
    if not isinstance(timezone_value, str):
        return None
    if ")" in timezone_value:
        return timezone_value.split(")", 1)[1].strip() or None
    return timezone_value.strip() or None
