from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .activity_format import METERS_PER_MILE
from .storage import read_json_file, write_json_file
from .storage_paths import RACE_RESULTS_PATH
from .strava_store import activity_local_date
from .time_format import human_datetime

RESULTS_PATH = RACE_RESULTS_PATH

STANDARD_DISTANCES = {
    "1 mile": 1609.344,
    "mile": 1609.344,
    "5k": 5000.0,
    "10k": 10000.0,
    "half marathon": 21097.5,
    "marathon": 42195.0,
}


def save_race_result(
    *,
    race_name: str,
    race_date: str,
    distance: str,
    time: str,
    source: str = "athlete",
    path: Path = RESULTS_PATH,
) -> dict[str, Any]:
    race_name = race_name.strip()
    race_date = race_date.strip()
    distance_label, distance_meters = parse_race_distance(distance)
    seconds = parse_race_time(time)
    source = source.strip() or "athlete"
    if not race_name:
        raise RuntimeError("Race name cannot be empty.")
    if not race_date:
        raise RuntimeError("Race date cannot be empty.")

    result = {
        "race_name": race_name,
        "race_date": race_date,
        "distance": distance_label,
        "distance_meters": distance_meters,
        "time": format_race_time(seconds),
        "time_seconds": seconds,
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    results = [item for item in load_race_results(path) if _result_key(item) != _result_key(result)]
    results.append(result)
    results.sort(key=lambda item: str(item.get("race_date") or ""), reverse=True)
    write_json_file(path, {"results": results}, trailing_newline=True)
    return result


def load_race_results(path: Path = RESULTS_PATH) -> list[dict[str, Any]]:
    data = read_json_file(path, default={}, suppress_errors=True)
    if not isinstance(data, dict):
        return []
    results = data.get("results")
    return results if isinstance(results, list) else []


def race_results_context(path: Path = RESULTS_PATH, limit: int = 5) -> str:
    results = load_race_results(path)
    if not results:
        return "No official race results have been saved yet."
    lines = ["Official race results saved by the athlete:"]
    for result in results[:limit]:
        updated_at = human_datetime(result.get("updated_at"))
        lines.append(
            "- "
            f"{result.get('race_date', '?')}: {result.get('race_name', 'Race')}, "
            f"{result.get('distance', '?')} in {result.get('time', '?')} "
            f"(source: {result.get('source', 'athlete')}, saved {updated_at})"
        )
    return "\n".join(lines)


def official_result_for_activity(activity: dict[str, Any]) -> dict[str, Any] | None:
    activity_date = activity_local_date(activity)
    if activity_date is None:
        return None
    activity_name = str(activity.get("name") or "").lower()
    same_date = [
        result
        for result in load_race_results()
        if str(result.get("race_date") or "") == activity_date.isoformat()
    ]
    if not same_date:
        return None
    named = [
        result
        for result in same_date
        if _name_tokens(str(result.get("race_name") or "")) <= _name_tokens(activity_name)
    ]
    return (named or same_date)[0]


def parse_race_distance(distance: str) -> tuple[str, float]:
    raw = distance.strip()
    normalized = raw.lower().replace(" ", "")
    if normalized in {"5k", "10k"}:
        return normalized.upper(), STANDARD_DISTANCES[normalized]
    lowered = raw.lower()
    if lowered in STANDARD_DISTANCES:
        label = "1 mile" if lowered == "mile" else lowered.title()
        return label, STANDARD_DISTANCES[lowered]
    miles_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:mi|mile|miles)", lowered)
    if miles_match:
        miles = float(miles_match.group(1))
        return f"{miles:g} mi", miles * METERS_PER_MILE
    raise RuntimeError(f"Unsupported race distance: {distance!r}")


def parse_race_time(time: str) -> int:
    parts = time.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise RuntimeError(f"Unsupported race time: {time!r}")
    try:
        values = [int(part) for part in parts]
    except ValueError as exc:
        raise RuntimeError(f"Unsupported race time: {time!r}") from exc
    if any(value < 0 for value in values):
        raise RuntimeError(f"Unsupported race time: {time!r}")
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        minutes, seconds = values
        return minutes * 60 + seconds
    hours, minutes, seconds = values
    return hours * 3600 + minutes * 60 + seconds


def format_race_time(seconds: int) -> str:
    if seconds < 0:
        raise RuntimeError("Race time cannot be negative.")
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _result_key(result: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(result.get("race_date") or ""),
        str(result.get("race_name") or "").strip().lower(),
        str(result.get("distance") or "").strip().lower(),
    )


def _name_tokens(name: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", name.lower()) if len(token) > 2}
