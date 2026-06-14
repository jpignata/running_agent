from __future__ import annotations

import contextvars
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEBUG_STDOUT_ENV = "RUNNING_AGENT_DEBUG_LOG"
QUIET_STDOUT_ENV = "RUNNING_AGENT_QUIET_LOG"
TRACE_STDOUT_ENV = "RUNNING_AGENT_TRACE_LOG"

_ACTIVE_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "running_agent_trace_id",
    default=None,
)


def log_event(event_type: str, fields: dict[str, Any]) -> None:
    if _quiet_stdout_enabled():
        return
    trace_id = _ACTIVE_TRACE_ID.get()
    if trace_id and "trace_id" not in fields:
        fields = {"trace_id": trace_id, **fields}
    entry = {
        "type": event_type,
        **fields,
    }
    if _should_print_event(event_type):
        print(_event_line(entry), flush=True)


@dataclass
class InteractionTrace:
    trace_id: str
    source: str
    interaction: str
    started_monotonic: float
    _token: contextvars.Token
    _fields: dict[str, Any] = field(default_factory=dict)
    _closed: bool = False

    def add(self, **fields: Any) -> None:
        self._fields.update(fields)

    def close(self, status: str = "ok", **fields: Any) -> None:
        if self._closed:
            return
        self._closed = True
        self._fields.update(fields)
        duration_ms = int((time.monotonic() - self.started_monotonic) * 1000)
        log_event(
            "trace_end",
            {
                "trace_id": self.trace_id,
                "source": self.source,
                "interaction": self.interaction,
                "status": status,
                "duration_ms": duration_ms,
                **self._fields,
            },
        )
        _ACTIVE_TRACE_ID.reset(self._token)


def start_trace(source: str, interaction: str, **fields: Any) -> InteractionTrace:
    trace_id = _new_trace_id(source)
    token = _ACTIVE_TRACE_ID.set(trace_id)
    trace = InteractionTrace(
        trace_id=trace_id,
        source=source,
        interaction=interaction,
        started_monotonic=time.monotonic(),
        _token=token,
    )
    log_event(
        "trace_start",
        {
            "trace_id": trace_id,
            "source": source,
            "interaction": interaction,
            **fields,
        },
    )
    return trace


def _event_line(entry: dict[str, Any]) -> str:
    parts = [str(entry.get("type"))]
    for key, value in entry.items():
        if key == "type":
            continue
        parts.append(f"{key}={_line_value(value, quoted=key == 'text')}")
    return " ".join(parts)


def _line_value(value: Any, quoted: bool = False) -> str:
    text = str(value).replace("\\", "\\\\").replace("\n", "\\n")
    if quoted:
        text = text.replace('"', '\\"')
        return f'"{text}"'
    return text


def _debug_stdout_enabled() -> bool:
    return os.environ.get(DEBUG_STDOUT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _trace_stdout_enabled() -> bool:
    return os.environ.get(TRACE_STDOUT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _quiet_stdout_enabled() -> bool:
    return os.environ.get(QUIET_STDOUT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _should_print_event(event_type: str) -> bool:
    if event_type == "debug":
        return _debug_stdout_enabled()
    if event_type.startswith("trace_"):
        return _trace_stdout_enabled()
    return True


def _new_trace_id(source: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_source = "".join(char if char.isalnum() else "-" for char in source.lower()).strip("-")
    suffix = uuid.uuid4().hex[:6]
    return f"{stamp}-{safe_source or 'trace'}-{suffix}"
