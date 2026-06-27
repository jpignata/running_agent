from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from .activity_format import detailed_activity_context
from .activity_format import miles as activity_miles
from .activity_format import recent_runs_context
from .coach_log import append_week_review, coach_log_context
from .feedback import summarize_training
from .garmin_context import safe_garmin_weekly_context
from .goal_readiness import goal_readiness_context, goal_readiness_snapshot
from .goal_readiness_history import save_goal_readiness_history_entry
from .goal_store import training_goal_context
from .openai_client import coaching_reply
from .plan_store import (
    load_weekly_plan,
    parse_weekly_plan,
    planned_workout_for_date,
    weekly_plan_context_for_week,
    weekly_plan_history_for_week,
)
from .strava_client import StravaClient
from .weather_client import safe_enrich_activity_weather
from .workout_classifier import classify_workout

DETAIL_RUN_LIMIT = 4
QUALITY_NAME_WORDS = ("track", "tempo", "interval", "workout", "threshold", "fartlek", "race")
REST_DAY_WORDS = ("rest", "off", "cross", "strength", "mobility", "yoga")


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
    facts = reviewed_week_facts_context(activities, week_start, week_end)
    recent_runs = f"{recent_runs}\n\n{facts}"
    garmin_context = safe_garmin_weekly_context(days=7)
    readiness_snapshot = goal_readiness_snapshot(activities=activities, days=lookback_days)
    readiness_context = goal_readiness_context(readiness_snapshot)
    prompt = (
        f"Review the athlete's training week from {week_start.isoformat()} through "
        f"{week_end.isoformat()} for use before suggesting next week's plan. Write like a real "
        "coach texting the athlete, not like a report. Start with a natural sentence such as "
        "'You had a great week,' 'This was a solid week,' or 'This was a challenging week,' "
        "based on the data. Do not use a title, section headers, markdown, or label-style "
        "phrases like 'Takeaway:' or 'By weekday:'. Use the reviewed-week deterministic facts "
        "for completed mileage and plan-comparison claims. If those facts say no reviewed-week "
        "plan or no planned mileage is available, do not say the athlete was over plan, under "
        "plan, short of plan, or missed planned mileage. Compare the saved weekly plan with what "
        "was completed only when the deterministic facts support that comparison; otherwise note "
        "mileage, quality sessions, long run, extra work, and "
        "Garmin recovery patterns. Use detailed lap context when it is "
        "provided for structured workouts, tempos, races, or long runs. Interpret Garmin data "
        "against the week: low readiness after quality work can be normal, while repeated poor "
        "sleep, elevated resting HR, low HRV, high stress, unusual Body Battery, or failed "
        "workouts may indicate recovery debt. Use the deterministic goal-readiness snapshot for "
        "PR-progress claims: name what this week improved, what gap remains, and what next "
        "checkpoint would raise confidence. Use its readiness bucket unless the week's evidence "
        "clearly changes the interpretation, and do not say the athlete is on track, behind, or "
        "missing the goal unless the snapshot and completed week support that. End with one "
        "concise coaching takeaway that should guide next week's plan, "
        "but phrase it conversationally. Keep it plain text and under 220 words."
    )

    try:
        reviewed_week_plan = weekly_plan_context_for_week(week_start, prefer_history=True)
        review = coaching_reply(
            prompt,
            training_summary=summarize_training(activities, days=lookback_days),
            recent_runs=recent_runs,
            weekly_plan=_review_context_sections(
                reviewed_week_plan=reviewed_week_plan,
            ),
            training_goal=training_goal_context(),
            goal_readiness=readiness_context,
            coach_log=_labeled_section("Coach log", coach_log_context()),
            garmin_context=garmin_context,
            tools_enabled=False,
        )
    except RuntimeError as error:
        review = _fallback_week_review(activities, garmin_context, error)

    if log_review:
        append_week_review(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            summary=review,
        )
        save_goal_readiness_history_entry(
            week_start=week_start.isoformat(),
            snapshot=readiness_snapshot,
        )

    return review


def weekly_coaching_message(
    client: StravaClient,
    week_start: date,
    target_week_start: date,
    lookback_days: int = 42,
    log_review: bool = True,
) -> str:
    week_end = week_start + timedelta(days=6)
    target_week_end = target_week_start + timedelta(days=6)
    activities = client.recent_activities(days=lookback_days)
    recent_runs = recent_runs_context(activities, limit=20)
    detailed_runs = weekly_quality_detail_context(client, activities, week_start, week_end)
    if detailed_runs:
        recent_runs = f"{recent_runs}\n\nDetailed quality/long-run context:\n{detailed_runs}"
    facts = reviewed_week_facts_context(activities, week_start, week_end)
    recent_runs = f"{recent_runs}\n\n{facts}"
    garmin_context = safe_garmin_weekly_context(days=7)
    readiness_snapshot = goal_readiness_snapshot(activities=activities, days=lookback_days)
    readiness_context = goal_readiness_context(readiness_snapshot)
    prompt = (
        f"Write one integrated Sunday evening coaching message for Telegram. Review the week "
        f"from {week_start.isoformat()} through {week_end.isoformat()}, then handle next "
        f"week for {target_week_start.isoformat()} through {target_week_end.isoformat()}. "
        "This should feel like one natural note from a real coach, not two pasted reports. "
        "Start with a natural read on the week, such as 'You had a great week,' 'This was a "
        "solid week,' or 'This was a challenging week,' based on the data. Do not use a title, "
        "section headers, markdown, or label-style phrases like 'Weekly review:', 'Next week:', "
        "'Takeaway:', 'By weekday:', or 'Why this setup:'. "
        "Use the reviewed-week deterministic facts for completed mileage and plan-comparison "
        "claims. If those facts say no reviewed-week plan or no planned mileage is available, "
        "do not say the athlete was over plan, under plan, short of plan, or missed planned "
        "mileage. Compare a reviewed-week saved plan with what was completed only when the "
        "deterministic facts support that comparison; otherwise cover mileage, quality "
        "sessions, long run, extra work, and Garmin recovery patterns. Use detailed "
        "lap context when provided for structured workouts, tempos, races, or long runs. "
        "Use the deterministic goal-readiness snapshot for PR-progress claims: name what this "
        "week improved, what gap remains, and what next checkpoint would raise confidence. Use "
        "its readiness bucket unless the week's evidence clearly changes the interpretation, and "
        "do not say the athlete is on track, behind, or missing the goal unless the snapshot and "
        "completed week support that. "
        "Use the labeled reviewed-week plan only to judge the completed week. Use the labeled "
        "target-week plan only for forward guidance. If the target-week plan section says there "
        "is a saved weekly plan for the target week, recap "
        "that saved plan instead of suggesting a different one. In that case, explain briefly why "
        "it fits or what to watch, but do not replace it. If there is no saved target-week plan, transition "
        "naturally into a specific Monday-through-Sunday plan. Any new suggested plan must "
        "respect progression: estimate the just-finished week's completed mileage, cap next "
        "week at about 8% above that unless the athlete explicitly asked for more, and make "
        "the daily mileage add up to that cap. If last week was 38 miles, keep next week at "
        "41 miles or less. Do not write mileage ranges whose high ends could exceed the cap. "
        "Use Garmin as recovery context without overreacting to one bad day. Keep hard days "
        "balanced with easy/recovery days, keep the plan practical, and do not claim it has "
        "been saved. Do not end with an offer to make another version or add exact paces. "
        "Keep it plain text, conversational, and concise."
    )

    reviewed_week_plan = weekly_plan_context_for_week(week_start, prefer_history=True)
    target_week_plan = weekly_plan_context_for_week(target_week_start)
    message = coaching_reply(
        prompt,
        training_summary=summarize_training(activities, days=lookback_days),
        recent_runs=recent_runs,
        weekly_plan=_review_context_sections(
            reviewed_week_plan=reviewed_week_plan,
            target_week_plan=target_week_plan,
        ),
        training_goal=training_goal_context(),
        goal_readiness=readiness_context,
        coach_log=_labeled_section("Coach log", coach_log_context()),
        garmin_context=garmin_context,
        tools_enabled=False,
    )

    if log_review:
        append_week_review(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            summary=message,
        )
        save_goal_readiness_history_entry(
            week_start=week_start.isoformat(),
            snapshot=readiness_snapshot,
        )

    return message


def current_week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def _review_context_sections(
    *,
    reviewed_week_plan: str,
    target_week_plan: str | None = None,
) -> str:
    sections = [_labeled_section("Reviewed-week plan", reviewed_week_plan)]
    if target_week_plan is not None:
        sections.append(_labeled_section("Target-week plan", target_week_plan))
    return "\n\n".join(sections)


def _labeled_section(title: str, body: str) -> str:
    return f"{title}:\n{body}"


def reviewed_week_facts_context(
    activities: list[dict[str, Any]],
    week_start: date,
    week_end: date,
) -> str:
    runs = [
        activity
        for activity in activities
        if activity.get("type") == "Run"
        and (run_date := _activity_local_date(activity)) is not None
        and week_start <= run_date <= week_end
    ]
    completed_miles = sum(activity_miles(run) for run in runs)
    lines = [
        "Reviewed-week deterministic facts:",
        f"- Reviewed window: {week_start.isoformat()} through {week_end.isoformat()}.",
        f"- Completed synced runs in reviewed window: {len(runs)}.",
        f"- Completed synced mileage in reviewed window: {completed_miles:.1f} mi.",
    ]

    planned_miles, planned_note = _reviewed_week_planned_mileage(week_start)
    lines.append(f"- Reviewed-week plan status: {planned_note}")
    if planned_miles is not None:
        delta = completed_miles - planned_miles
        lines.append(f"- Explicit planned mileage: {planned_miles:.1f} mi.")
        lines.append(f"- Completed minus explicit planned mileage: {delta:+.1f} mi.")
    else:
        lines.append("- Explicit planned mileage: unavailable.")
        lines.append("- Completed versus planned mileage: unavailable.")
    lines.append(
        "- Do not claim missed, under-plan, over-plan, or short-of-plan mileage unless "
        "explicit planned mileage is available above."
    )
    return "\n".join(lines)


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
        detailed = safe_enrich_activity_weather(detailed)
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


def _reviewed_week_planned_mileage(week_start: date) -> tuple[float | None, str]:
    plan = weekly_plan_history_for_week(week_start) or load_weekly_plan()
    if not plan:
        return None, "no saved reviewed-week plan."
    if plan.get("week_start") != week_start.isoformat():
        return None, "no saved plan explicitly applies to the reviewed week."
    text = plan.get("text", "").strip()
    if not text:
        return None, "reviewed-week plan is empty."

    parsed = parse_weekly_plan(text)
    if not parsed:
        return None, "reviewed-week plan has no parseable day lines."

    total = 0.0
    unavailable_days: list[str] = []
    for weekday in WEEKDAYS_IN_ORDER:
        workout = parsed.get(weekday)
        if not workout:
            continue
        miles = _planned_miles_from_workout(workout)
        if miles is None:
            unavailable_days.append(weekday)
            continue
        total += miles

    if unavailable_days:
        return (
            None,
            "reviewed-week plan exists, but planned mileage is not explicit for "
            + ", ".join(unavailable_days)
            + ".",
        )
    return total, "reviewed-week plan exists and explicit mileage was parsed."


WEEKDAYS_IN_ORDER = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _planned_miles_from_workout(workout: str) -> float | None:
    normalized = workout.strip().lower()
    if not normalized:
        return None
    if any(word in f" {normalized} " for word in REST_DAY_WORDS):
        return 0.0
    if _has_unmeasured_workout_components(normalized):
        return None

    explicit_miles = [
        float(match.group(1))
        for match in re.finditer(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*(?:mi|mile|miles)\b", normalized)
    ]
    if explicit_miles:
        return sum(explicit_miles)

    bare = re.match(
        r"^(\d+(?:\.\d+)?)\s+(?:easy|recovery|steady|long|progression|tempo)\b", normalized
    )
    if bare:
        return float(bare.group(1))
    return None


def _has_unmeasured_workout_components(workout: str) -> bool:
    if re.search(r"\b\d+\s*x\s*\d+(?:m|k)\b", workout):
        return True
    if re.search(r"\b(?:cd|cooldown|cool down)\b", workout) and not re.search(
        r"\d+(?:\.\d+)?\s*(?:mi|mile|miles)\s*(?:cd|cooldown|cool down)\b",
        workout,
    ):
        return True
    return False


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
