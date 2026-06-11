from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .activity_format import recent_runs_context
from .coach_log import read_coach_log
from .feedback import summarize_training
from .garmin_context import safe_garmin_weekly_context
from .goal_store import training_goal_context
from .pace_calibration import save_pace_calibration
from .plan_store import weekly_plan_context
from .storage import read_json_file, write_json_file
from .storage_paths import COACH_REFLECTION_PATH
from .strava_client import StravaClient
from .time_format import human_datetime
from .vdot import race_vdot_context

REFLECTION_PATH = COACH_REFLECTION_PATH


def save_coach_reflection(reflection_text: str, path: Path = REFLECTION_PATH) -> dict[str, Any]:
    reflection_text = reflection_text.strip()
    if not reflection_text:
        raise RuntimeError("Coach reflection text cannot be empty.")

    reflection = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "text": reflection_text,
    }
    write_json_file(path, reflection)
    return reflection


def load_coach_reflection(path: Path = REFLECTION_PATH) -> dict[str, Any] | None:
    return read_json_file(path, default=None)


def coach_reflection_context(path: Path = REFLECTION_PATH) -> str:
    reflection = load_coach_reflection(path)
    if not reflection:
        return "No coach reflection has been recorded yet."
    updated_at = human_datetime(reflection.get("updated_at"))
    text = reflection.get("text", "").strip()
    if not text:
        return "No coach reflection has been recorded yet."
    return f"Current coach reflection, last updated {updated_at}:\n{text}"


def generate_coach_reflection(
    client: StravaClient,
    lookback_days: int = 42,
) -> str:
    from .openai_client import coaching_reply

    activities = client.recent_activities(days=lookback_days)
    prompt = (
        "Rewrite the coach's private current thesis about this athlete for future model prompts. "
        "Use compact labeled bullets, not essay prose and not a user-facing coaching voice. Use "
        "recent Strava runs, Garmin trend context, the saved weekly plan, the overall goal, the "
        "coach log, and the previous reflection. Focus on durable coaching judgment, not a recap. "
        "Include these labels exactly: Capacity, Working VDOT/pace calibration, Goal confidence, "
        "Goal requirements/checkpoints, Current limiter, Next emphasis, Watch items. Under "
        "Working VDOT/pace calibration, use any deterministic race-derived VDOT context as the "
        "numeric starting point. Then use representative races, controlled quality workouts, "
        "longer-term aerobic patterns, and caveats to set confidence and decide whether to be "
        "more conservative; include practical pace anchors when evidence supports them. "
        "Use Daniels-style pace category names precisely: Easy, Marathon, Threshold, Interval, "
        "and Repetition. Do not label 10K pace, controlled long reps, or cruise intervals as "
        "Interval pace; if useful, call them 10K/long-rep support separately. If there is not "
        "enough evidence to set true Interval or Repetition paces, omit them rather than "
        "inventing them or using a slower support pace under the wrong label. "
        "Under Goal requirements/checkpoints, compare the athlete's current working VDOT/pace "
        "calibration to the saved goal pace. If there is a gap, state it plainly and describe "
        "the fitness adaptations or checkpoints needed to close it, such as higher sustainable "
        "volume, longer long runs, stronger threshold durability, marathon-pace segment "
        "tolerance, or improved recovery consistency. Translate the saved goal into concrete "
        "adaptations or timeline checkpoints that would make the goal more credible; use ranges "
        "and confidence language when uncertain, and do not invent a race date if one is not "
        "saved. Do not treat the goal pace as current fitness unless the evidence supports it. "
        "Under Watch items, include confidence words "
        "such as high/medium/low when a claim is a hypothesis. Keep the whole reflection under "
        "180 words. Do not store user preferences or goals here unless they matter to the "
        "coaching thesis."
    )
    reflection = coaching_reply(
        prompt,
        training_summary=summarize_training(activities, days=lookback_days),
        recent_runs=recent_runs_context(activities, limit=20),
        weekly_plan=weekly_plan_context(),
        training_goal=training_goal_context(),
        coach_log=(
            f"{reflection_coach_log_context()}\n\n"
            f"Previous coach reflection:\n{_reflection_without_pace_calibration(coach_reflection_context())}"
        ),
        garmin_context=safe_garmin_weekly_context(days=14),
        tools_enabled=False,
        include_coach_reflection=False,
        pace_calibration_text=race_vdot_context(activities),
        max_output_tokens=450,
    )
    save_coach_reflection(reflection)
    pace_calibration = _pace_calibration_from_reflection(reflection)
    if pace_calibration:
        save_pace_calibration(pace_calibration)
    return reflection


def _pace_calibration_from_reflection(reflection_text: str) -> str:
    lines = reflection_text.strip().splitlines()
    capture = False
    captured: list[str] = []
    labels = {
        "Capacity",
        "Working VDOT/pace calibration",
        "Goal confidence",
        "Goal requirements/checkpoints",
        "Current limiter",
        "Next emphasis",
        "Watch items",
    }
    for line in lines:
        stripped = line.strip()
        label = stripped.split(":", 1)[0]
        if label == "Working VDOT/pace calibration":
            capture = True
            after = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            if after:
                captured.append(after)
            continue
        if capture and label in labels and ":" in stripped:
            break
        if capture and stripped:
            captured.append(stripped)
    return "\n".join(captured).strip()


def _reflection_without_pace_calibration(reflection_text: str) -> str:
    lines = reflection_text.strip().splitlines()
    output: list[str] = []
    skipping = False
    labels = {
        "Capacity",
        "Working VDOT/pace calibration",
        "Goal confidence",
        "Goal requirements/checkpoints",
        "Current limiter",
        "Next emphasis",
        "Watch items",
    }
    for line in lines:
        stripped = line.strip()
        label = stripped.split(":", 1)[0]
        if label == "Working VDOT/pace calibration":
            skipping = True
            continue
        if skipping and label in labels and ":" in stripped:
            skipping = False
        if not skipping:
            output.append(line)
    return "\n".join(output).strip()


def reflection_coach_log_context(limit_runs: int = 12) -> str:
    entries = read_coach_log()
    if not entries:
        return "No coach log entries have been recorded yet."

    latest_week_review = next(
        (entry for entry in reversed(entries) if entry.get("type") == "week_reviewed"),
        None,
    )
    runs = _deduped_run_entries(entries)[-limit_runs:]

    lines = ["Coach log context for reflection:"]
    if latest_week_review:
        lines.append(
            "- latest weekly review "
            f"{latest_week_review.get('week_start', '?')} to "
            f"{latest_week_review.get('week_end', '?')}: "
            f"{latest_week_review.get('summary', '').strip()}"
        )
    for entry in runs:
        lines.append(
            "- "
            f"{entry.get('run_date', 'unknown date')}: "
            f"planned: {entry.get('planned_workout', '-')}; "
            f"completed: {entry.get('completed_run', '-')}"
        )
    return "\n".join(lines)


def _deduped_run_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    deduped = []
    for entry in reversed(entries):
        if entry.get("type") != "run_completed":
            continue
        key = entry.get("activity_id") or (entry.get("run_date"), entry.get("completed_run"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return list(reversed(deduped))
