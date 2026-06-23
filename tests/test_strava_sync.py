from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.strava_store import load_run_detail, load_run_summaries
from running_agent.strava_sync import save_synced_run_detail, sync_strava_runs


class StravaSyncTest(unittest.TestCase):
    def test_sync_strava_runs_saves_run_summaries_and_fetches_missing_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summaries_path = Path(tmp) / "activities.json"
            details_dir = Path(tmp) / "details"
            client = _FakeStrava(
                [
                    {"id": 1, "type": "Run", "name": "Run"},
                    {"id": 2, "type": "Ride", "name": "Ride"},
                ],
                details={1: {"id": 1, "name": "Run", "laps": []}},
            )

            result = sync_strava_runs(
                client,
                days=30,
                summaries_path=summaries_path,
                details_dir=details_dir,
            )
            second_result = sync_strava_runs(
                client,
                days=30,
                summaries_path=summaries_path,
                details_dir=details_dir,
            )

            self.assertEqual(result, {"runs_seen": 1, "summaries_saved": 1, "details_fetched": 1})
            self.assertEqual(
                second_result,
                {"runs_seen": 1, "summaries_saved": 1, "details_fetched": 0},
            )
            self.assertEqual(client.detail_requests, [1])
            self.assertEqual(set(load_run_summaries(summaries_path)), {"1"})
            self.assertEqual(load_run_detail(1, details_dir)["name"], "Run")

    def test_save_synced_run_detail_stores_summary_and_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summaries_path = Path(tmp) / "activities.json"
            details_dir = Path(tmp) / "details"

            save_synced_run_detail(
                {"id": 7, "type": "Run", "name": "Morning Run"},
                {"name": "Morning Run", "laps": []},
                summaries_path=summaries_path,
                details_dir=details_dir,
            )

            self.assertEqual(load_run_summaries(summaries_path)["7"]["name"], "Morning Run")
            self.assertEqual(load_run_detail(7, details_dir)["id"], 7)

    @patch(
        "running_agent.strava_sync.safe_enrich_activity_weather",
        side_effect=RuntimeError("weather down"),
    )
    def test_save_synced_run_detail_ignores_weather_failures(self, _weather) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summaries_path = Path(tmp) / "activities.json"
            details_dir = Path(tmp) / "details"

            save_synced_run_detail(
                {"id": 7, "type": "Run", "name": "Morning Run"},
                {"id": 7, "name": "Morning Run", "laps": []},
                summaries_path=summaries_path,
                details_dir=details_dir,
            )

            self.assertEqual(load_run_detail(7, details_dir)["name"], "Morning Run")


class _FakeStrava:
    def __init__(self, activities: list[dict], details: dict[int, dict]):
        self.activities = activities
        self.details = details
        self.detail_requests: list[int] = []

    def recent_activities(self, days: int) -> list[dict]:
        return self.activities

    def detailed_activity(self, activity_id: int) -> dict:
        self.detail_requests.append(activity_id)
        return self.details[activity_id]


if __name__ == "__main__":
    unittest.main()
