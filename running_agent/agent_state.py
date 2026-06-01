from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import read_json_file, write_json_file
from .storage_paths import STATE_PATH


def load_agent_state(path: Path = STATE_PATH) -> dict[str, Any]:
    state = read_json_file(path, default={})
    return state if isinstance(state, dict) else {}


def save_agent_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    write_json_file(path, state)
