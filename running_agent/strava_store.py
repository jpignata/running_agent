from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .storage import read_json_file, write_json_file
from .storage_paths import RACE_RESULTS_PATH, STRAVA_ACTIVITIES_PATH, STRAVA_DETAILS_DIR

RACE_WORKOUT_TYPE = 1


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


def local_store_health(
    summaries_path: Path = STRAVA_ACTIVITIES_PATH,
    details_dir: Path = STRAVA_DETAILS_DIR,
    race_results_path: Path = RACE_RESULTS_PATH,
) -> dict[str, Any]:
    summaries = list_run_summaries(summaries_path)
    race_results = _load_official_race_results(race_results_path)
    details_count = len(list(details_dir.glob("*.json"))) if details_dir.exists() else 0
    missing_details = [
        activity
        for activity in summaries
        if activity.get("id") is not None and not run_detail_exists(activity["id"], details_dir)
    ]
    race_like = [
        activity
        for activity in summaries
        if looks_like_race(activity) or _official_result_matches_activity(activity, race_results)
    ]
    return {
        "last_sync": _file_mtime(summaries_path),
        "activity_count": len(summaries),
        "detail_count": details_count,
        "missing_detail_count": len(missing_details),
        "missing_details": missing_details,
        "latest_race_like": race_like[:5],
        "race_results": race_results[:5],
        "repair_action": _repair_action(summaries, missing_details),
    }


def format_local_store_health(report: dict[str, Any]) -> str:
    lines = [
        "Local Strava store health",
        f"Last sync: {report.get('last_sync') or 'never'}",
        f"Activities: {report.get('activity_count', 0)}",
        f"Detailed activities: {report.get('detail_count', 0)}",
        f"Missing details: {report.get('missing_detail_count', 0)}",
    ]

    missing_details = _list_value(report.get("missing_details"))
    if missing_details:
        lines.append("Missing detail activity IDs: " + _activity_id_list(missing_details[:10]))

    race_like = _list_value(report.get("latest_race_like"))
    lines.append("Latest race-like activities:")
    if race_like:
        for activity in race_like:
            lines.append(f"- {_activity_label(activity)}")
    else:
        lines.append("- none")

    race_results = _list_value(report.get("race_results"))
    lines.append("Official saved race results:")
    if race_results:
        for result in race_results:
            lines.append(f"- {_race_result_label(result)}")
    else:
        lines.append("- none")

    repair_action = report.get("repair_action")
    lines.append(f"Repair action: {repair_action or 'none'}")
    return "\n".join(lines)


def looks_like_race(activity: dict[str, Any]) -> bool:
    return activity.get("workout_type") == RACE_WORKOUT_TYPE


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


def _file_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _load_official_race_results(path: Path) -> list[dict[str, Any]]:
    data = read_json_file(path, default={}, suppress_errors=True)
    if not isinstance(data, dict):
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    return sorted(results, key=lambda item: str(item.get("race_date") or ""), reverse=True)


def _official_result_matches_activity(
    activity: dict[str, Any],
    race_results: list[dict[str, Any]],
) -> bool:
    activity_date = activity_local_date(activity)
    if activity_date is None:
        return False
    activity_tokens = _name_tokens(str(activity.get("name") or ""))
    for result in race_results:
        if str(result.get("race_date") or "") != activity_date.isoformat():
            continue
        result_tokens = _name_tokens(str(result.get("race_name") or ""))
        if result_tokens and result_tokens <= activity_tokens:
            return True
    return False


def _name_tokens(value: str) -> set[str]:
    return {token for token in value.lower().replace("&", " ").split() if token}


def _repair_action(
    summaries: list[dict[str, Any]],
    missing_details: list[dict[str, Any]],
) -> str | None:
    if not summaries:
        return "Run `python -m running_agent sync-strava --days 365` to build the local store."
    if missing_details:
        return "Run `python -m running_agent sync-strava --days 365` to fetch missing details."
    return None


def _list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _activity_id_list(activities: list[dict[str, Any]]) -> str:
    return ", ".join(str(activity.get("id")) for activity in activities)


def _activity_label(activity: dict[str, Any]) -> str:
    activity_id = activity.get("id", "?")
    name = activity.get("name") or "Unnamed run"
    activity_date = activity_local_date(activity)
    date_text = activity_date.isoformat() if activity_date else "unknown date"
    return f"id {activity_id}: {date_text}, {name}"


def _race_result_label(result: dict[str, Any]) -> str:
    race_date = result.get("race_date") or "unknown date"
    race_name = result.get("race_name") or "Race"
    distance = result.get("distance") or "?"
    time = result.get("time") or "?"
    return f"{race_date}: {race_name}, {distance} in {time}"
