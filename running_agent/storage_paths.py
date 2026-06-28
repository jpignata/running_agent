from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(".data")

ATHLETE_PROFILE_PATH = DATA_DIR / "athlete_profile.txt"
COACH_LOG_PATH = DATA_DIR / "coach_log.jsonl"
COACH_REFLECTION_PATH = DATA_DIR / "coach_reflection.json"
GARMIN_SNAPSHOTS_PATH = DATA_DIR / "garmin_snapshots.json"
GOAL_READINESS_HISTORY_PATH = DATA_DIR / "goal_readiness_history.json"
PACE_CALIBRATION_PATH = DATA_DIR / "pace_calibration.json"
RACE_RESULTS_PATH = DATA_DIR / "race_results.json"
RUN_FEEDBACK_PATH = DATA_DIR / "run_feedback.jsonl"
RUN_MEMORY_PATH = DATA_DIR / "run_memory.json"
STATE_PATH = DATA_DIR / "state.json"
STRAVA_ACTIVITIES_PATH = DATA_DIR / "strava" / "activities.json"
STRAVA_DETAILS_DIR = DATA_DIR / "strava" / "details"
TRAINING_GOAL_PATH = DATA_DIR / "training_goal.json"
WEEKLY_PLAN_PATH = DATA_DIR / "weekly_plan.json"
WEEKLY_PLAN_HISTORY_PATH = DATA_DIR / "weekly_plan_history.json"
WEEKLY_NOTES_PATH = DATA_DIR / "weekly_notes.jsonl"


def prepare_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
