from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .garmin_client import GarminClient
from .storage_paths import GARMIN_SNAPSHOTS_PATH, prepare_parent

DEFAULT_RETENTION_DAYS = 90


def refresh_garmin_snapshots(
    client: GarminClient | None = None,
    end_date: date | None = None,
    days: int = 45,
    path: Path = GARMIN_SNAPSHOTS_PATH,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, Any]:
    client = client or GarminClient()
    end_date = end_date or date.today()
    snapshots = load_garmin_snapshots(path)

    for target_date in _date_range(end_date, days):
        snapshots[target_date.isoformat()] = client.readiness_snapshot(
            target_date=target_date,
            vo2max_lookback_days=0,
        )

    snapshots = _prune_snapshots(snapshots, end_date=end_date, retention_days=retention_days)
    save_garmin_snapshots(snapshots, path)
    return snapshots


def cached_garmin_snapshots(
    end_date: date,
    days: int,
    path: Path = GARMIN_SNAPSHOTS_PATH,
) -> list[dict[str, Any]]:
    snapshots = load_garmin_snapshots(path)
    return [
        snapshots[date_key]
        for date_key in (target_date.isoformat() for target_date in _date_range(end_date, days))
        if isinstance(snapshots.get(date_key), dict)
    ]


def load_garmin_snapshots(path: Path = GARMIN_SNAPSHOTS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_garmin_snapshots(
    snapshots: dict[str, Any],
    path: Path = GARMIN_SNAPSHOTS_PATH,
) -> None:
    prepare_parent(path)
    path.write_text(json.dumps(snapshots, indent=2, sort_keys=True) + "\n")


def _date_range(end_date: date, days: int) -> list[date]:
    if days <= 0:
        return []
    return [end_date - timedelta(days=offset) for offset in reversed(range(days))]


def _prune_snapshots(
    snapshots: dict[str, Any],
    end_date: date,
    retention_days: int,
) -> dict[str, Any]:
    if retention_days <= 0:
        return snapshots
    cutoff = end_date - timedelta(days=retention_days - 1)
    return {
        date_key: snapshot
        for date_key, snapshot in snapshots.items()
        if _parse_date(date_key) is None or _parse_date(date_key) >= cutoff
    }


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
