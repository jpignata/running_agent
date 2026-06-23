from __future__ import annotations

from datetime import date
from typing import Any

from .activity_format import detailed_activity_context
from .feedback import summarize_training
from .goal_store import training_goal_context
from .heart_rate import observed_max_heart_rate
from .openai_client import coaching_reply
from .plan_store import weekly_plan_context_for_date
from .strava_client import StravaClient
from .weather_client import safe_enrich_activity_weather

DEFAULT_SEARCH_DAYS = 120


def run_summary_for_date(
    client: StravaClient,
    target_date: date,
    search_days: int = DEFAULT_SEARCH_DAYS,
    lookback_days: int = 21,
) -> str:
    activities = client.runs_on_date(target_date, search_days=search_days)
    if not activities:
        raise RuntimeError(f"No Strava runs found on {target_date.isoformat()}.")
    if len(activities) > 1:
        selected_note = f"Found {len(activities)} runs on {target_date.isoformat()}; summarizing the latest one."
    else:
        selected_note = ""

    activity = activities[0]
    detailed = client.detailed_activity(activity["id"])
    detailed = safe_enrich_activity_weather(detailed)
    recent_activities = client.recent_activities(days=max(lookback_days, 21))
    max_heart_rate = observed_max_heart_rate([*recent_activities, detailed])
    prompt = (
        f"Write a natural post-run coaching text for Telegram about this Strava run from "
        f"{target_date.strftime('%A, %B %-d, %Y')}. Do not use a title, header, markdown, or "
        "label-style opener. Start like a coach reacting to the workout, with the core run "
        "facts woven into the first sentence. Use lap-by-lap data to identify workout "
        "structure and pacing when this was a quality or structured session. If it was an easy "
        "or steady aerobic run, keep the lap analysis light. Compare against the matching "
        "weekly plan day when available, and give one practical next step. If Garmin context is "
        "available through the shared coach prompt, use it as supporting context only; do not "
        "treat low readiness after a hard effort as automatically concerning."
    )

    try:
        note = coaching_reply(
            prompt,
            training_summary=summarize_training(recent_activities, days=lookback_days),
            recent_runs=detailed_activity_context(
                detailed,
                target_date=target_date,
                max_heart_rate=max_heart_rate,
            ),
            weekly_plan=weekly_plan_context_for_date(target_date),
            training_goal=training_goal_context(),
            tools_enabled=False,
        )
    except RuntimeError as error:
        note = _fallback_summary(detailed, error, max_heart_rate=max_heart_rate)

    parts = []
    if selected_note:
        parts.append(selected_note)
    parts.append(note)
    return "\n\n".join(parts)


def _fallback_summary(
    activity: dict[str, Any],
    error: RuntimeError,
    *,
    max_heart_rate: int | None = None,
) -> str:
    return (
        f"AI coaching was unavailable ({error}).\n\n"
        f"{detailed_activity_context(activity, max_heart_rate=max_heart_rate)}\n\n"
        "Basic read: use the lap table to compare the session against the planned workout, "
        "then keep the next run easy if this was a quality day or if the effort ran hot."
    )
