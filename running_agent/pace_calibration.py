from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import read_json_file, write_json_file
from .storage_paths import PACE_CALIBRATION_PATH
from .time_format import human_datetime

PACE_PATH = PACE_CALIBRATION_PATH


def save_pace_calibration(calibration_text: str, path: Path = PACE_PATH) -> dict[str, Any]:
    calibration_text = calibration_text.strip()
    if not calibration_text:
        raise RuntimeError("Pace calibration text cannot be empty.")

    calibration = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "text": calibration_text,
    }
    write_json_file(path, calibration)
    return calibration


def load_pace_calibration(path: Path = PACE_PATH) -> dict[str, Any] | None:
    return read_json_file(path, default=None)


def pace_calibration_context(path: Path = PACE_PATH) -> str:
    calibration = load_pace_calibration(path)
    if not calibration:
        return "No pace calibration has been saved yet."
    updated_at = human_datetime(calibration.get("updated_at"))
    text = calibration.get("text", "").strip()
    if not text:
        return "No pace calibration has been saved yet."
    return f"Current VDOT and pace calibration, last updated {updated_at}:\n{text}"
