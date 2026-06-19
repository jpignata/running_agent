from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .coach_time import coach_today
from .storage import append_jsonl, read_jsonl
from .storage_paths import RUN_FEEDBACK_PATH


def clean_post_run_feedback(raw_text: str, normalized: dict[str, Any]) -> dict[str, Any]:
    feedback: dict[str, Any] = {"raw": raw_text.strip()}
    rpe = normalized.get("rpe")
    if isinstance(rpe, int) and 1 <= rpe <= 10:
        feedback["rpe"] = rpe
    for key in ("legs", "notes"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            feedback[key] = value.strip().lower()
    pain = _clean_pain(normalized.get("pain"))
    if pain:
        feedback["pain"] = pain
    return feedback


def _clean_pain(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned in {"no", "none", "no pain", "none noted", "nothing", "n/a", "na"}:
        return "no"
    if cleaned.startswith("no ") and ("pain" in cleaned or "soreness" in cleaned):
        return "no"
    return cleaned


def append_post_run_feedback(
    text: str,
    *,
    normalized: dict[str, Any] | None = None,
    activity_id: Any = None,
    run_date: str | None = None,
    path: Path = RUN_FEEDBACK_PATH,
) -> dict[str, Any]:
    feedback = clean_post_run_feedback(text, normalized or {"notes": text})
    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": "post_run_feedback",
        "activity_id": activity_id,
        "run_date": run_date or coach_today().isoformat(),
        **feedback,
    }
    append_jsonl(path, entry)
    return entry


def read_post_run_feedback(path: Path = RUN_FEEDBACK_PATH) -> list[dict[str, Any]]:
    return read_jsonl(path)


def post_run_feedback_context(path: Path = RUN_FEEDBACK_PATH, limit: int = 6) -> str:
    entries = read_post_run_feedback(path)
    if not entries:
        return "No post-run feedback has been recorded yet."

    lines = ["Recent post-run feedback:"]
    for entry in entries[-limit:]:
        parts = [str(entry.get("run_date") or "unknown date")]
        if entry.get("rpe") is not None:
            parts.append(f"RPE {entry['rpe']}")
        if entry.get("legs"):
            parts.append(f"legs {entry['legs']}")
        if entry.get("pain"):
            parts.append(f"pain {entry['pain']}")
        if entry.get("notes"):
            parts.append(str(entry["notes"]))
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines)
