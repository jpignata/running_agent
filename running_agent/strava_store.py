from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from .storage import read_json_file, write_json_file
from .storage_paths import STRAVA_ACTIVITIES_PATH, STRAVA_DETAILS_DIR


def load_run_summaries(path: Path = STRAVA_ACTIVITIES_PATH) -> dict[str, dict[str, Any]]:
    data = read_json_file(path, default={}, suppress_errors=True)
    return data if isinstance(data, dict) else {}


def save_run_summaries(
    summaries: dict[str, dict[str, Any]],
    path: Path = STRAVA_ACTIVITIES_PATH,
) -> None:
    write_json_file(path, summaries, trailing_newline=True)


def list_run_summaries(path: Path = STRAVA_ACTIVITIES_PATH) -> list[dict[str, Any]]:
    return sorted(load_run_summaries(path).values(), key=activity_start_timestamp, reverse=True)


def save_run_detail(
    activity: dict[str, Any],
    details_dir: Path = STRAVA_DETAILS_DIR,
) -> None:
    activity_id = activity.get("id")
    if activity_id is None:
        raise RuntimeError("Cannot save Strava activity detail without an id.")
    write_json_file(_detail_path(activity_id, details_dir), activity, trailing_newline=True)


def load_run_detail(
    activity_id: int | str,
    details_dir: Path = STRAVA_DETAILS_DIR,
) -> dict[str, Any] | None:
    data = read_json_file(
        _detail_path(activity_id, details_dir), default=None, suppress_errors=True
    )
    return data if isinstance(data, dict) else None


def run_detail_exists(activity_id: int | str, details_dir: Path = STRAVA_DETAILS_DIR) -> bool:
    return _detail_path(activity_id, details_dir).exists()


def activity_local_date(activity: dict[str, Any]) -> date | None:
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def activity_start_timestamp(activity: dict[str, Any]) -> float:
    value = activity.get("start_date") or activity.get("start_date_local")
    if not value:
        return 0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def _detail_path(activity_id: int | str, details_dir: Path) -> Path:
    return details_dir / f"{activity_id}.json"
