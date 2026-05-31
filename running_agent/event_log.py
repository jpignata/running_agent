from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

DEBUG_STDOUT_ENV = "RUNNING_AGENT_DEBUG_LOG"


def log_event(event_type: str, fields: dict[str, Any]) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": timestamp,
        "type": event_type,
        **fields,
    }
    if event_type != "debug" or _debug_stdout_enabled():
        print(_event_line(entry), flush=True)


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
