from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import read_json_file, write_json_file
from .storage_paths import GOAL_READINESS_HISTORY_PATH

HISTORY_PATH = GOAL_READINESS_HISTORY_PATH


def save_goal_readiness_history_entry(
    *,
    week_start: str,
    snapshot: dict[str, Any],
    path: Path = HISTORY_PATH,
) -> dict[str, Any]:
    week_start = week_start.strip()
    if not week_start:
        raise RuntimeError("Goal readiness history week_start cannot be empty.")

    entry = {
        "week_start": week_start,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "goal": snapshot.get("goal"),
        "readiness_bucket": snapshot.get("readiness_bucket"),
        "main_gap": snapshot.get("main_gap"),
        "next_checkpoint": snapshot.get("next_checkpoint"),
        "current_anchor": snapshot.get("current_anchor"),
        "recent_mileage": snapshot.get("recent_mileage"),
        "longest_recent_run": snapshot.get("longest_recent_run"),
        "key_evidence": _key_evidence(snapshot),
    }
    entries = [
        item for item in load_goal_readiness_history(path) if item.get("week_start") != week_start
    ]
    entries.append(entry)
    entries.sort(key=lambda item: str(item.get("week_start") or ""))
    write_json_file(path, {"entries": entries}, trailing_newline=True)
    return entry


def load_goal_readiness_history(path: Path = HISTORY_PATH) -> list[dict[str, Any]]:
    data = read_json_file(path, default={}, suppress_errors=True)
    if not isinstance(data, dict):
        return []
    entries = data.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def goal_readiness_history_context(path: Path = HISTORY_PATH, limit: int = 4) -> str:
    entries = load_goal_readiness_history(path)
    if not entries:
        return "No goal readiness history has been recorded yet."

    lines = ["Recent goal readiness history:"]
    for entry in entries[-max(1, limit) :]:
        parts = [
            f"week {entry.get('week_start', '?')}",
            f"bucket {entry.get('readiness_bucket') or '?'}",
        ]
        if entry.get("main_gap"):
            parts.append(f"gap: {entry['main_gap']}")
        if entry.get("next_checkpoint"):
            parts.append(f"checkpoint: {entry['next_checkpoint']}")
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


def _key_evidence(snapshot: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    longest = snapshot.get("longest_recent_run")
    if isinstance(longest, str) and longest:
        evidence.append(f"Longest run: {longest}")
    mileage = snapshot.get("recent_mileage")
    if isinstance(mileage, dict):
        average = mileage.get("average_weekly_miles")
        total = mileage.get("total_miles")
        if average is not None and total is not None:
            evidence.append(f"Recent mileage: {total} mi total, {average} mi/week average")
    workouts = snapshot.get("key_workouts")
    if isinstance(workouts, list):
        evidence.extend(str(item) for item in workouts[:3] if item)
    risks = snapshot.get("feedback_risks")
    if isinstance(risks, list) and risks:
        evidence.extend(f"Risk: {item}" for item in risks[:2] if item)
    return evidence[:6]
