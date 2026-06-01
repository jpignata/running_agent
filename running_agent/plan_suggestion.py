from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .activity_format import recent_runs_context
from .coach_log import coach_log_context
from .coach_time import in_coach_time
from .feedback import summarize_training
from .garmin_context import safe_garmin_weekly_context
from .goal_store import training_goal_context
from .openai_client import coaching_reply
from .plan_store import weekly_plan_context
from .strava_client import StravaClient

SUNDAY = 6
SUNDAY_PLAN_HOUR = 18
PLAN_STATE_KEY = "last_next_week_plan_start"


def suggest_next_week_plan(
    client: StravaClient,
    target_week_start: date,
    lookback_days: int = 42,
) -> str:
    activities = client.recent_activities(days=lookback_days)
    target_week_end = target_week_start + timedelta(days=6)
    prompt = (
        "Suggest a new training plan idea for the upcoming week, "
        f"{target_week_start.isoformat()} through {target_week_end.isoformat()}. Write like a "
        "real coach texting the athlete, not like a formal plan document. Do not use a title, "
        "section headers, markdown, or labels like 'Why this setup:'. Start with a brief "
        "conversational bridge from the week review into the plan. "
        "The weekly plan below is the current or just-finished plan. Use it only as context for "
        "what the athlete was supposed to do recently. Do not copy it forward as the new plan. "
        "Adapt the next week based on recent Strava training, how the current plan appears to "
        "have gone, Garmin recovery context, and the overall goal. Use Garmin data as recovery "
        "context, but do not overreact to one bad day or generic absolute thresholds. Treat low "
        "readiness after hard training as potentially normal. Treat values like Body Battery as "
        "meaningful mainly when they are unusual for this athlete or align with other fatigue "
        "signals. Use the athlete-specific profile and coach log to decide which Garmin signals "
        "have actually mattered for this athlete. "
        "Make the plan appropriately challenging for the goal when recent execution supports it, "
        "and say plainly when the evidence does not yet support the athlete's stated goal or "
        "when a specific limiter needs to be developed first. Push the next useful adaptation "
        "rather than defaulting to caution, while keeping progression sensible. Weekly volume "
        "increases should usually stay around "
        "5-10%, and hard days should be balanced with easy or recovery days. Estimate the "
        "athlete's completed mileage from the just-finished week before proposing daily mileage. "
        "The proposed week's total should not exceed about 8% above the just-finished week's "
        "completed mileage unless the athlete explicitly asks for a bigger jump. If last week "
        "was 38 miles, keep the proposed total at 41 miles or less. Make the daily mileage add "
        "up to that cap; do not write ranges that could exceed the cap when summed. "
        "Keep the plan specific and practical. Include each day Monday through Sunday, but write "
        "the days as natural plain-text lines instead of headers. Include the rationale in the "
        "flow of the message, and do not claim the plan has been saved. Do not end with an offer "
        "to make another version or add exact paces."
    )

    try:
        note = coaching_reply(
            prompt,
            training_summary=summarize_training(activities, days=lookback_days),
            recent_runs=recent_runs_context(activities, limit=20),
            weekly_plan=weekly_plan_context(),
            training_goal=training_goal_context(),
            coach_log=coach_log_context(),
            garmin_context=safe_garmin_weekly_context(days=7),
        )
    except RuntimeError as error:
        note = _fallback_plan_note(error)

    return note


def should_send_sunday_plan(now: datetime, state: dict[str, Any]) -> bool:
    now = in_coach_time(now)
    if now.weekday() != SUNDAY or now.hour < SUNDAY_PLAN_HOUR:
        return False
    return state.get(PLAN_STATE_KEY) != next_week_start(now.date()).isoformat()


def mark_sunday_plan_sent(now: datetime, state: dict[str, Any]) -> None:
    now = in_coach_time(now)
    state[PLAN_STATE_KEY] = next_week_start(now.date()).isoformat()


def next_week_start(today: date) -> date:
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return today + timedelta(days=days_until_monday)


def _fallback_plan_note(error: RuntimeError) -> str:
    return (
        f"AI planning was unavailable ({error}).\n\n"
        "Basic plan idea:\n"
        "Monday: Rest or very easy recovery.\n"
        "Tuesday: Easy run with relaxed strides if you feel fresh.\n"
        "Wednesday: Easy aerobic run.\n"
        "Thursday: Controlled workout or steady run, not all-out.\n"
        "Friday: Rest or short recovery jog.\n"
        "Saturday: Long run at easy effort.\n"
        "Sunday: Recovery run or rest.\n\n"
        "Rationale: keep the week controlled until the coach can review recent training context."
    )
