from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_LOG_PATH = Path(".running_agent_events.jsonl")
DEBUG_STDOUT_ENV = "RUNNING_AGENT_DEBUG_LOG"


def log_event(event_type: str, fields: dict[str, Any], path: Path = EVENT_LOG_PATH) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": timestamp,
        "type": event_type,
        **fields,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    path.chmod(0o600)
    if event_type != "debug" or _debug_stdout_enabled():
        print(_event_line(entry), flush=True)


def read_event_log(path: Path = EVENT_LOG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def _event_line(entry: dict[str, Any]) -> str:
    parts = [str(entry.get("timestamp")), str(entry.get("type"))]
    for key, value in entry.items():
        if key in {"timestamp", "type"}:
            continue
        parts.append(f"{key}={_line_value(value)}")
    return " ".join(parts)


def _line_value(value: Any) -> str:
    return str(value).replace("\n", "\\n")


def _debug_stdout_enabled() -> bool:
    return os.environ.get(DEBUG_STDOUT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
