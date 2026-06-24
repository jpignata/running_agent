from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .activity_format import miles
from .coach_log import read_coach_log
from .coach_time import coach_today
from .goal_readiness_history import goal_readiness_history_context
from .goal_store import GOAL_PATH, load_training_goal
from .pace_calibration import PACE_PATH, load_pace_calibration
from .post_run_feedback import read_post_run_feedback
from .race_results import load_race_results, parse_race_time
from .storage_paths import (
    COACH_LOG_PATH,
    RACE_RESULTS_PATH,
    RUN_FEEDBACK_PATH,
    STRAVA_ACTIVITIES_PATH,
)
from .strava_store import activity_local_date, list_run_summaries, looks_like_race
from .vdot import race_vdot_estimates, vdot_from_performance

QUALITY_NAME_WORDS = (
    "track",
    "tempo",
    "interval",
    "workout",
    "threshold",
    "fartlek",
    "progression",
    "race",
    "5k",
    "10k",
    "mile",
)

MIN_WEEKLY_MILES = {
    "marathon": 35,
    "half marathon": 25,
    "10K": 20,
    "5K": 20,
    "mile": 15,
}

MIN_LONG_RUN_MILES = {
    "marathon": 16,
    "half marathon": 10,
    "10K": 8,
    "5K": 7,
    "mile": 6,
}


def goal_readiness_snapshot(
    *,
    today: date | None = None,
    days: int = 42,
    activities: list[dict[str, Any]] | None = None,
    goal_path: Path = GOAL_PATH,
    pace_path: Path = PACE_PATH,
    coach_log_path: Path = COACH_LOG_PATH,
    feedback_path: Path = RUN_FEEDBACK_PATH,
    race_results_path: Path = RACE_RESULTS_PATH,
    summaries_path: Path = STRAVA_ACTIVITIES_PATH,
) -> dict[str, Any]:
    today = today or coach_today()
    days = max(7, min(days, 365))
    cutoff = today - timedelta(days=days - 1)
    runs = _recent_runs(activities, summaries_path, cutoff, today)
    goal = load_training_goal(goal_path) or {}
    goal_text = str(goal.get("text") or "").strip()
    pace = load_pace_calibration(pace_path) or {}
    pace_text = str(pace.get("text") or "").strip()
    race_anchor = _race_anchor(runs, race_results_path)
    weekly_mileage = _weekly_mileage(runs)
    feedback = _recent_feedback(feedback_path, cutoff, today)
    risk_signals = _risk_signals(feedback)
    key_workouts = _key_workouts(runs, read_coach_log(coach_log_path), cutoff, today)
    longest = max(runs, key=miles) if runs else None
    main_gap = _main_gap(
        goal_text=goal_text,
        runs=runs,
        race_anchor=race_anchor,
        weekly_mileage=weekly_mileage,
        key_workouts=key_workouts,
        risk_signals=risk_signals,
    )
    bucket = _readiness_bucket(
        goal_text=goal_text,
        runs=runs,
        race_anchor=race_anchor,
        weekly_mileage=weekly_mileage,
        key_workouts=key_workouts,
        risk_signals=risk_signals,
    )
    return {
        "goal": _goal_summary(goal_text),
        "goal_text": goal_text or None,
        "days": days,
        "current_anchor": race_anchor,
        "pace_calibration": pace_text or None,
        "recent_mileage": _mileage_summary(weekly_mileage),
        "longest_recent_run": _activity_summary(longest) if longest else None,
        "key_workouts": key_workouts[:5],
        "feedback_risks": risk_signals,
        "main_gap": main_gap,
        "readiness_bucket": bucket,
        "next_checkpoint": _next_checkpoint(
            goal_text=goal_text,
            main_gap=main_gap,
            risk_signals=risk_signals,
            runs=runs,
            race_anchor=race_anchor,
            weekly_mileage=weekly_mileage,
            key_workouts=key_workouts,
        ),
    }


def goal_readiness_context(snapshot: dict[str, Any] | None = None, **kwargs: Any) -> str:
    snapshot = snapshot or goal_readiness_snapshot(**kwargs)
    lines = ["Goal readiness snapshot:"]
    lines.append(f"- Goal: {snapshot.get('goal') or 'No saved goal.'}")
    lines.append(f"- Readiness bucket: {snapshot.get('readiness_bucket')}")
    anchor = snapshot.get("current_anchor")
    lines.append(f"- Current anchor: {_anchor_text(anchor)}")
    mileage = snapshot.get("recent_mileage")
    if isinstance(mileage, dict):
        lines.append(
            "- Recent mileage: "
            f"{mileage.get('total_miles', 0):.1f} mi over {snapshot.get('days')} days; "
            f"average {mileage.get('average_weekly_miles', 0):.1f} mi/week."
        )
    longest = snapshot.get("longest_recent_run")
    lines.append(f"- Longest recent run: {longest or 'none'}")
    workouts = snapshot.get("key_workouts")
    if isinstance(workouts, list) and workouts:
        lines.append("- Key workout evidence: " + "; ".join(str(item) for item in workouts[:3]))
    else:
        lines.append("- Key workout evidence: none found in the recent local window.")
    risks = snapshot.get("feedback_risks")
    if isinstance(risks, list) and risks:
        lines.append("- Feedback/risk signals: " + "; ".join(str(item) for item in risks[:3]))
    else:
        lines.append("- Feedback/risk signals: none flagged from recent post-run feedback.")
    lines.append(f"- Main gap: {snapshot.get('main_gap')}")
    lines.append(f"- Next checkpoint: {snapshot.get('next_checkpoint')}")
    lines.append("")
    lines.append(goal_readiness_history_context())
    pace = snapshot.get("pace_calibration")
    if pace:
        lines.append(f"- Saved pace calibration: {pace}")
    return "\n".join(lines)


def _recent_runs(
    activities: list[dict[str, Any]] | None,
    summaries_path: Path,
    cutoff: date,
    today: date,
) -> list[dict[str, Any]]:
    source = activities if activities is not None else list_run_summaries(summaries_path)
    runs = []
    for activity in source:
        if activity.get("type") != "Run":
            continue
        run_date = activity_local_date(activity)
        if run_date is None or not cutoff <= run_date <= today:
            continue
        runs.append(activity)
    return sorted(runs, key=lambda activity: activity.get("start_date") or "", reverse=True)


def _goal_summary(goal_text: str) -> str | None:
    if not goal_text:
        return None
    distance = _goal_distance(goal_text)
    target_time = _target_time(goal_text)
    pieces = [goal_text]
    if distance:
        pieces.append(f"distance signal: {distance}")
    if target_time:
        pieces.append(f"target time signal: {target_time}")
    return " | ".join(pieces)


def _race_anchor(
    runs: list[dict[str, Any]],
    race_results_path: Path,
) -> dict[str, Any] | None:
    official = load_race_results(race_results_path)
    if official:
        result = sorted(official, key=lambda item: str(item.get("race_date") or ""), reverse=True)[
            0
        ]
        distance_meters = float(result.get("distance_meters") or 0)
        seconds = _result_seconds(result)
        vdot = (
            vdot_from_performance(distance_meters, seconds) if distance_meters and seconds else None
        )
        return {
            "name": result.get("race_name") or "Race",
            "date": result.get("race_date"),
            "distance": result.get("distance"),
            "time": result.get("time"),
            "source": "official saved race result",
            "vdot": round(vdot, 1) if vdot is not None else None,
        }
    estimates = race_vdot_estimates(runs)
    if not estimates:
        race_like = next((run for run in runs if looks_like_race(run)), None)
        return _activity_race_anchor(race_like) if race_like else None
    best = max(estimates, key=lambda estimate: estimate.vdot)
    return {
        "name": best.name,
        "date": str(
            activity_local_date(next((run for run in runs if run.get("name") == best.name), {}))
        ),
        "distance": best.race_label,
        "time": _duration(best.performance_seconds),
        "source": best.source,
        "vdot": round(best.vdot, 1),
    }


def _result_seconds(result: dict[str, Any]) -> int:
    seconds = result.get("time_seconds")
    if isinstance(seconds, int):
        return seconds
    try:
        return parse_race_time(str(result.get("time") or ""))
    except RuntimeError:
        return 0


def _activity_race_anchor(activity: dict[str, Any] | None) -> dict[str, Any] | None:
    if not activity:
        return None
    return {
        "name": activity.get("name") or "Race",
        "date": str(activity_local_date(activity)),
        "distance": f"{miles(activity):.2f} mi",
        "time": _duration(int(activity.get("moving_time") or activity.get("elapsed_time") or 0)),
        "source": "race-like local activity",
        "vdot": None,
    }


def _weekly_mileage(runs: list[dict[str, Any]]) -> dict[str, float]:
    weekly: dict[str, float] = defaultdict(float)
    for run in runs:
        run_date = activity_local_date(run)
        if run_date is None:
            continue
        week_start = run_date - timedelta(days=run_date.weekday())
        weekly[week_start.isoformat()] += miles(run)
    return dict(sorted(weekly.items()))


def _mileage_summary(weekly_mileage: dict[str, float]) -> dict[str, Any]:
    total = sum(weekly_mileage.values())
    weeks = len(weekly_mileage)
    return {
        "total_miles": round(total, 1),
        "average_weekly_miles": round(total / weeks, 1) if weeks else 0.0,
        "weeks": weekly_mileage,
    }


def _recent_feedback(path: Path, cutoff: date, today: date) -> list[dict[str, Any]]:
    entries = []
    for entry in read_post_run_feedback(path):
        entry_date = _date_from_text(str(entry.get("run_date") or ""))
        if entry_date is None or cutoff <= entry_date <= today:
            entries.append(entry)
    return entries


def _risk_signals(feedback: list[dict[str, Any]]) -> list[str]:
    signals: list[str] = []
    for entry in feedback[-8:]:
        run_date = entry.get("run_date") or "unknown date"
        pain = str(entry.get("pain") or "").strip()
        rpe = entry.get("rpe")
        legs = str(entry.get("legs") or "").strip()
        if pain and pain != "no":
            signals.append(f"{run_date}: pain noted ({pain})")
        if isinstance(rpe, int) and rpe >= 8:
            signals.append(f"{run_date}: high RPE {rpe}")
        if legs in {"heavy", "dead", "sore", "tired"}:
            signals.append(f"{run_date}: legs {legs}")
    return signals[:5]


def _key_workouts(
    runs: list[dict[str, Any]],
    coach_log: list[dict[str, Any]],
    cutoff: date,
    today: date,
) -> list[str]:
    evidence: list[str] = []
    for run in runs:
        name = str(run.get("name") or "Run")
        lowered = name.lower()
        if looks_like_race(run) or any(word in lowered for word in QUALITY_NAME_WORDS):
            evidence.append(_activity_summary(run))
    for entry in coach_log[-12:]:
        if entry.get("type") != "run_completed":
            continue
        run_date = _date_from_text(str(entry.get("run_date") or ""))
        if run_date is not None and not cutoff <= run_date <= today:
            continue
        planned = str(entry.get("planned_workout") or "")
        completed = str(entry.get("completed_run") or "")
        if planned and "no matching planned workout" not in planned.lower():
            evidence.append(f"{entry.get('run_date')}: planned {planned}; completed {completed}")
    return _dedupe(evidence)


def _activity_summary(activity: dict[str, Any]) -> str:
    run_date = activity_local_date(activity)
    distance = miles(activity)
    name = activity.get("name") or "Run"
    return f"{run_date.isoformat() if run_date else 'unknown date'}: {name}, {distance:.1f} mi"


def _main_gap(
    *,
    goal_text: str,
    runs: list[dict[str, Any]],
    race_anchor: dict[str, Any] | None,
    weekly_mileage: dict[str, float],
    key_workouts: list[str],
    risk_signals: list[str],
) -> str:
    if not goal_text:
        return "No saved goal, so PR readiness cannot be judged yet."
    if risk_signals:
        return "Recent feedback has fatigue or pain signals; prove recovery before forcing PR-specific work."
    if not runs:
        return "No recent local runs are available for readiness evidence."
    if not race_anchor:
        return "No recent race or official result anchor is available for goal-specific confidence."
    goal_distance = _goal_distance(goal_text)
    average_weekly = _mileage_summary(weekly_mileage)["average_weekly_miles"]
    minimum_weekly = MIN_WEEKLY_MILES.get(goal_distance or "", 20)
    if average_weekly < minimum_weekly:
        return (
            f"Recent volume is still light for the {goal_distance or 'goal'}; "
            "consistency and aerobic base are the main gap."
        )
    longest = _longest_miles(runs)
    minimum_long_run = MIN_LONG_RUN_MILES.get(goal_distance or "", 0)
    if minimum_long_run and longest < minimum_long_run:
        return (
            f"Long-run durability is still the main gap for the {goal_distance}; "
            f"recent longest run is {longest:.1f} mi."
        )
    if not key_workouts:
        return "Recent volume exists, but there is not enough race-specific workout evidence yet."
    if goal_distance == "marathon":
        return (
            "Need marathon-specific proof: fueling, controlled long-run rhythm, and the ability "
            "to touch marathon pace without turning it into a race."
        )
    if goal_distance == "half marathon":
        return (
            "Need threshold durability: controlled sustained work that supports half-marathon pace."
        )
    if goal_distance == "10K":
        return "Need threshold-to-10K rhythm proof: controlled work near race demand without overreaching."
    if goal_distance == "5K":
        return "Need 5K pace tolerance proof: repeatable work near race rhythm without fading late."
    if goal_distance == "mile":
        return "Need speed and mechanics proof: fast relaxed reps without excessive fatigue."
    return "Need the next checkpoint to show the target pace or distance-specific demand is repeatable."


def _readiness_bucket(
    *,
    goal_text: str,
    runs: list[dict[str, Any]],
    race_anchor: dict[str, Any] | None,
    weekly_mileage: dict[str, float],
    key_workouts: list[str],
    risk_signals: list[str],
) -> str:
    if not goal_text or not runs:
        return "too early to judge"
    if risk_signals:
        return "at risk"
    if not race_anchor:
        return "building"
    average_weekly = _mileage_summary(weekly_mileage)["average_weekly_miles"]
    if average_weekly >= 25 and key_workouts:
        return "plausible with clear gaps"
    return "building"


def _next_checkpoint(
    *,
    goal_text: str,
    main_gap: str,
    risk_signals: list[str],
    runs: list[dict[str, Any]],
    race_anchor: dict[str, Any] | None,
    weekly_mileage: dict[str, float],
    key_workouts: list[str],
) -> str:
    if risk_signals:
        return "First checkpoint is a pain-free easy run or recovery day response before adding proof work."
    if not runs:
        return (
            "First checkpoint is a consistent week of easy running with one controlled longer run."
        )
    if not race_anchor:
        return "Tune-up race or controlled time trial to create a current performance anchor."

    goal_distance = _goal_distance(goal_text)
    average_weekly = _mileage_summary(weekly_mileage)["average_weekly_miles"]
    minimum_weekly = MIN_WEEKLY_MILES.get(goal_distance or "", 20)
    if average_weekly < minimum_weekly:
        return (
            "Consistent mileage week before a bigger proof workout: build aerobic volume "
            "without adding another hard stimulus."
        )

    longest = _longest_miles(runs)
    minimum_long_run = MIN_LONG_RUN_MILES.get(goal_distance or "", 0)
    if minimum_long_run and longest < minimum_long_run:
        if goal_distance == "marathon":
            return "Controlled long run progression with practiced fueling before adding marathon-pace segments."
        return (
            "Controlled longer run that proves durability before adding sharper race-specific work."
        )

    if not key_workouts:
        return _first_quality_checkpoint(goal_distance)

    if goal_distance == "marathon":
        return "Long run with practiced fueling and controlled marathon-pace segments, kept comfortably below race effort."
    if goal_distance == "half marathon":
        return "Threshold progression or long run with a controlled moderate finish to prove half-marathon durability."
    if goal_distance == "10K":
        return "Threshold progression with controlled 10K-rhythm work, such as cruise intervals that stay repeatable."
    if goal_distance == "mile":
        return "Controlled repetition session that proves speed and mechanics without turning into a race."
    if goal_distance == "5K":
        return "Controlled 5 x 1K or 3 x mile near 5K rhythm with recoveries that keep the work repeatable."
    return "A goal-specific workout that tests the main limiter without requiring a race effort."


def _first_quality_checkpoint(goal_distance: str | None) -> str:
    if goal_distance == "marathon":
        return (
            "Steady medium-long run or moderate-finish long run before adding marathon-pace proof."
        )
    if goal_distance == "half marathon":
        return "Controlled threshold session, such as cruise intervals, to establish half-marathon support."
    if goal_distance == "10K":
        return (
            "Controlled threshold-to-10K session, such as 4-5 x 5 minutes, without racing the reps."
        )
    if goal_distance == "5K":
        return "Controlled 5K-rhythm workout, such as 5 x 1K, with repeatable recoveries."
    if goal_distance == "mile":
        return "Relaxed repetition session with full recovery to prove speed and mechanics."
    return "Controlled quality workout matched to the goal distance."


def _longest_miles(runs: list[dict[str, Any]]) -> float:
    if not runs:
        return 0.0
    return max(miles(run) for run in runs)


def _goal_distance(goal_text: str) -> str | None:
    lowered = goal_text.lower()
    matches: list[tuple[int, str]] = []
    for label, pattern in (
        ("half marathon", r"\bhalf\s+marathon\b"),
        ("marathon", r"\bmarathon\b"),
        ("10K", r"\b10\s*k\b"),
        ("5K", r"\b5\s*k\b"),
        ("mile", r"\bmile\b"),
    ):
        match = re.search(pattern, lowered)
        if match:
            matches.append((match.start(), label))
    if not matches:
        return None
    return min(matches)[1]


def _target_time(goal_text: str) -> str | None:
    lowered = goal_text.lower()
    marker = "sub-"
    index = lowered.find(marker)
    if index >= 0:
        return goal_text[index + len(marker) :].split()[0].strip(".,;")
    return None


def _date_from_text(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _duration(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _anchor_text(anchor: object) -> str:
    if not isinstance(anchor, dict) or not anchor:
        return "none"
    vdot = anchor.get("vdot")
    vdot_text = f", VDOT {vdot}" if vdot is not None else ""
    return (
        f"{anchor.get('date') or 'unknown date'}: {anchor.get('name') or 'Race'}, "
        f"{anchor.get('distance') or '?'} in {anchor.get('time') or '?'} "
        f"from {anchor.get('source') or 'unknown source'}{vdot_text}"
    )


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
