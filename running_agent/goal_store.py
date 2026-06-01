from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage_paths import TRAINING_GOAL_PATH, prepare_parent
from .time_format import human_datetime

GOAL_PATH = TRAINING_GOAL_PATH


def save_training_goal(goal_text: str, path: Path = GOAL_PATH) -> dict[str, Any]:
    goal_text = goal_text.strip()
    if not goal_text:
        raise RuntimeError("Training goal text cannot be empty.")

    goal = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "text": goal_text,
    }
    prepare_parent(path)
    path.write_text(json.dumps(goal, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return goal


def load_training_goal(path: Path = GOAL_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def training_goal_context(path: Path = GOAL_PATH) -> str:
    goal = load_training_goal(path)
    if not goal:
        return "No overall training goal has been provided."
    updated_at = human_datetime(goal.get("updated_at"))
    text = goal.get("text", "").strip()
    if not text:
        return "No overall training goal has been provided."
    return f"Overall training goal, last updated {updated_at}:\n{text}"
