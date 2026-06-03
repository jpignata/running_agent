from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage_paths import STRAVA_ACTIVITIES_PATH, STRAVA_DETAILS_DIR
from .strava_client import StravaClient
from .strava_store import (
    load_run_summaries,
    run_detail_exists,
    save_run_detail,
    save_run_summaries,
)


def sync_strava_runs(
    client: StravaClient | None = None,
    days: int = 365,
    summaries_path: Path = STRAVA_ACTIVITIES_PATH,
    details_dir: Path = STRAVA_DETAILS_DIR,
) -> dict[str, int]:
    client = client or StravaClient()
    days = max(1, min(days, 3650))
    activities = client.recent_activities(days=days)
    runs = [
        activity
        for activity in activities
        if activity.get("type") == "Run" and activity.get("id") is not None
    ]
    summaries = load_run_summaries(summaries_path)
    details_fetched = 0

    for run in runs:
        activity_id = str(run["id"])
        summaries[activity_id] = run
        if not run_detail_exists(activity_id, details_dir):
            detail = client.detailed_activity(run["id"])
            if isinstance(detail, dict):
                if "id" not in detail:
                    detail = {**detail, "id": run["id"]}
                save_run_detail(detail, details_dir)
                details_fetched += 1

    save_run_summaries(summaries, summaries_path)
    return {
        "runs_seen": len(runs),
        "summaries_saved": len(runs),
        "details_fetched": details_fetched,
    }


def save_synced_run_detail(
    summary: dict[str, Any],
    detail: dict[str, Any],
    summaries_path: Path = STRAVA_ACTIVITIES_PATH,
    details_dir: Path = STRAVA_DETAILS_DIR,
) -> None:
    activity_id = summary.get("id") or detail.get("id")
    if activity_id is None:
        return
    if "id" not in detail:
        detail = {**detail, "id": activity_id}
    summaries = load_run_summaries(summaries_path)
    summaries[str(activity_id)] = summary
    save_run_summaries(summaries, summaries_path)
    save_run_detail(detail, details_dir)
