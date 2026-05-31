from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .activity_format import detailed_activity_context, recent_runs_context
from .coach_log import append_week_review, coach_log_context
from .feedback import summarize_training
from .garmin_context import safe_garmin_weekly_context
from .goal_store import training_goal_context
from .openai_client import coaching_reply
from .plan_store import planned_workout_for_date, weekly_plan_context
from .strava_client import StravaClient
from .workout_classifier import classify_workout

DETAIL_RUN_LIMIT = 4
QUALITY_NAME_WORDS = ("track", "tempo", "interval", "workout", "threshold", "fartlek", "race")


def review_week(
    client: StravaClient,
    week_start: date,
    lookback_days: int = 7,
    log_review: bool = True,
) -> str:
    week_end = week_start + timedelta(days=6)
    activities = client.recent_activities(days=lookback_days)
    recent_runs = recent_runs_context(activities, limit=12)
    detailed_runs = weekly_quality_detail_context(client, activities, week_start, week_end)
    if detailed_runs:
        recent_runs = f"{recent_runs}\n\nDetailed quality/long-run context:\n{detailed_runs}"
    garmin_context = safe_garmin_weekly_context(days=7)
    prompt = (
        f"Review the athlete's training week from {week_start.isoformat()} through "
        f"{week_end.isoformat()} for use before suggesting next week's plan. Write like a real "
        "coach texting the athlete, not like a report. Start with a natural sentence such as "
        "'You had a great week,' 'This was a solid week,' or 'This was a challenging week,' "
        "based on the data. Do not use a title, section headers, markdown, or label-style "
        "phrases like 'Takeaway:' or 'By weekday:'. Compare the saved weekly plan with what "
        "was completed, note mileage, quality sessions, long run, missed or extra work, and "
        "Garmin recovery patterns. Use detailed lap context when it is "
        "provided for structured workouts, tempos, races, or long runs. Interpret Garmin data "
        "against the week: low readiness after quality work can be normal, while repeated poor "
        "sleep, elevated resting HR, low HRV, high stress, unusual Body Battery, or failed "
        "workouts may indicate recovery debt. End with one concise coaching takeaway that should "
        "guide next week's plan, but phrase it conversationally. Keep it plain text and under "
        "220 words."
    )

    try:
        review = coaching_reply(
            prompt,
            training_summary=summarize_training(activities, days=lookback_days),
            recent_runs=recent_runs,
            weekly_plan=weekly_plan_context(),
            training_goal=training_goal_context(),
            coach_log=coach_log_context(),
            garmin_context=garmin_context,
        )
    except RuntimeError as error:
        review = _fallback_week_review(activities, garmin_context, error)

    if log_review:
        append_week_review(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            summary=review,
        )

    return review


def current_week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def weekly_quality_detail_context(
    client: StravaClient,
    activities: list[dict[str, Any]],
    week_start: date,
    week_end: date,
    limit: int = DETAIL_RUN_LIMIT,
) -> str:
    selected = [
        activity
        for activity in activities
        if _activity_local_date(activity)
        and week_start <= _activity_local_date(activity) <= week_end
        and _should_include_lap_context(activity, _activity_local_date(activity))
    ][:limit]
    if not selected:
        return ""

    contexts: list[str] = []
    for activity in selected:
        activity_id = activity.get("id")
        run_date = _activity_local_date(activity)
        if activity_id is None or run_date is None:
            continue
        try:
            detailed = client.detailed_activity(activity_id)
        except RuntimeError as error:
            contexts.append(
                f"{run_date.isoformat()} {activity.get('name', 'Run')}: detail unavailable ({error})."
            )
            continue
        contexts.append(detailed_activity_context(detailed, max_laps=30, target_date=run_date))
    return "\n\n---\n\n".join(contexts)


def _should_include_lap_context(activity: dict[str, Any], run_date: date | None) -> bool:
    if activity.get("type") != "Run" or run_date is None:
        return False
    planned = planned_workout_for_date(run_date)
    classification, _reason, _emphasis = classify_workout(activity, planned)
    if classification in {"structured workout", "race", "long run"}:
        return True
    name = f" {activity.get('name', '').lower()} "
    return any(word in name for word in QUALITY_NAME_WORDS)


def _activity_local_date(activity: dict[str, Any]) -> date | None:
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _fallback_week_review(
    activities: list[dict],
    garmin_context: str,
    error: RuntimeError,
) -> str:
    return (
        f"AI weekly review was unavailable ({error}).\n\n"
        f"{summarize_training(activities, days=7)}\n\n"
        f"{garmin_context}\n\n"
        "Coaching takeaway: make next week appropriately challenging if recovery and recent "
        "execution support it, while keeping progression controlled."
    )
