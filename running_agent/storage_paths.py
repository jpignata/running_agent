from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(".data")

ATHLETE_PROFILE_PATH = DATA_DIR / "athlete_profile.txt"
COACH_LOG_PATH = DATA_DIR / "coach_log.jsonl"
STATE_PATH = DATA_DIR / "state.json"
TRAINING_GOAL_PATH = DATA_DIR / "training_goal.json"
WEEKLY_PLAN_PATH = DATA_DIR / "weekly_plan.json"


def prepare_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
