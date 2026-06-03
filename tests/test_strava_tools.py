from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from running_agent.strava_tools import get_local_run_details, query_local_runs

METERS_PER_MILE = 1609.344


class StravaToolsTest(unittest.TestCase):
    @patch("running_agent.strava_tools.coach_today", return_value=date(2026, 6, 3))
    @patch("running_agent.strava_tools.load_run_detail", return_value={"id": 2})
    @patch("running_agent.strava_tools.list_run_summaries")
    def test_query_local_runs_filters_race_like_runs(
        self,
        list_run_summaries,
        _load_run_detail,
        _coach_today,
    ) -> None:
        list_run_summaries.return_value = [
            _run(1, "Easy Run", 5, "2026-05-30T06:00:00Z"),
            _run(2, "Memorial Day 10K Race", 6.2, "2026-05-25T07:00:00Z"),
            _run(3, "Turkey Trot", 3.1, "2025-11-27T08:00:00Z", workout_type=1),
        ]

        result = query_local_runs(days=365, limit=3, races_only=True)

        self.assertIn("id 2: Memorial Day 10K Race: 6.20 mi", result)
        self.assertIn("id 3: Turkey Trot: 3.10 mi", result)
        self.assertNotIn("Easy Run", result)

    @patch("running_agent.strava_tools.coach_today", return_value=date(2026, 6, 3))
    @patch("running_agent.strava_tools.load_run_detail", return_value=None)
    @patch("running_agent.strava_tools.list_run_summaries")
    def test_query_local_runs_matches_query_terms(
        self,
        list_run_summaries,
        _load_run_detail,
        _coach_today,
    ) -> None:
        list_run_summaries.return_value = [
            _run(2, "Memorial Day 10K Race", 6.2, "2026-05-25T07:00:00Z"),
            _run(3, "Turkey Trot", 3.1, "2025-11-27T08:00:00Z", workout_type=1),
        ]

        result = query_local_runs(query="turkey")

        self.assertIn("id 3: Turkey Trot: 3.10 mi", result)
        self.assertNotIn("Memorial Day", result)

    @patch("running_agent.strava_tools.coach_today", return_value=date(2026, 6, 3))
    @patch("running_agent.strava_tools.load_run_detail")
    @patch("running_agent.strava_tools.list_run_summaries")
    def test_get_local_run_details_returns_synced_laps(
        self,
        list_run_summaries,
        load_run_detail,
        _coach_today,
    ) -> None:
        run = _run(4, "Track Workout", 7.0, "2026-06-03T06:00:00Z")
        list_run_summaries.return_value = [run]
        load_run_detail.return_value = {
            **run,
            "laps": [
                {
                    "name": "Lap 1",
                    "distance": 400,
                    "moving_time": 80,
                    "average_heartrate": 145,
                }
            ],
        }

        result = get_local_run_details(selector="latest_run")

        self.assertIn("Track Workout: 7.00 mi", result)
        self.assertIn("Lap data from Strava detailed activity", result)
        self.assertIn("? | 0.25 mi | 1:20", result)

    @patch("running_agent.strava_tools.coach_today", return_value=date(2026, 6, 3))
    @patch("running_agent.strava_tools.load_run_detail")
    @patch("running_agent.strava_tools.list_run_summaries")
    def test_get_local_run_details_handles_last_week_track_workout_query(
        self,
        list_run_summaries,
        load_run_detail,
        _coach_today,
    ) -> None:
        today_track = _run(4, "Track", 7.0, "2026-06-03T06:00:00Z")
        last_week_track = _run(5, "Track", 7.9, "2026-05-27T06:00:00Z")
        list_run_summaries.return_value = [today_track, last_week_track]
        load_run_detail.return_value = {**last_week_track, "laps": []}

        result = get_local_run_details(selector="query", query="track workout last week", days=21)

        self.assertIn("Track: 7.90 mi", result)
        self.assertIn("Historical plan note", result)
        self.assertNotIn("Matched planned workout", result)
        load_run_detail.assert_called_once_with(5)


def _run(
    activity_id: int,
    name: str,
    miles: float,
    start_date_local: str,
    workout_type: int | None = None,
) -> dict:
    activity = {
        "id": activity_id,
        "type": "Run",
        "name": name,
        "distance": miles * METERS_PER_MILE,
        "moving_time": int(miles * 8 * 60),
        "start_date_local": start_date_local,
    }
    if workout_type is not None:
        activity["workout_type"] = workout_type
    return activity


if __name__ == "__main__":
    unittest.main()
