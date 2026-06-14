from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from running_agent.coach_time import COACH_TIME_ZONE
from running_agent.feedback import summarize_training
from running_agent.time_format import human_datetime

METERS_PER_MILE = 1609.344


class FeedbackAndTimeTest(unittest.TestCase):
    @patch(
        "running_agent.time_format.coach_now",
        return_value=datetime(2026, 5, 29, 11, 30, tzinfo=COACH_TIME_ZONE),
    )
    def test_human_datetime_formats_recent_timestamp_as_minutes_ago(self, _coach_now) -> None:
        self.assertEqual(human_datetime("2026-05-29T15:10:00+00:00"), "20 minutes ago")

    @patch(
        "running_agent.time_format.coach_now",
        return_value=datetime(2026, 5, 29, 15, 10, tzinfo=COACH_TIME_ZONE),
    )
    def test_human_datetime_formats_same_day_timestamp_as_hours_ago(self, _coach_now) -> None:
        self.assertEqual(human_datetime("2026-05-29T15:10:00+00:00"), "4 hours ago")

    @patch(
        "running_agent.time_format.coach_now",
        return_value=datetime(2026, 6, 1, 10, 0, tzinfo=COACH_TIME_ZONE),
    )
    def test_human_datetime_formats_nearby_timestamp_as_days_ago(self, _coach_now) -> None:
        self.assertEqual(human_datetime("2026-05-29T15:10:00+00:00"), "2 days ago")

    @patch(
        "running_agent.time_format.coach_now",
        return_value=datetime(2026, 7, 1, 10, 0, tzinfo=COACH_TIME_ZONE),
    )
    def test_human_datetime_uses_absolute_fallback_for_old_timestamp(self, _coach_now) -> None:
        formatted = human_datetime("2026-05-29T15:10:00+00:00")

        self.assertEqual(formatted, "on Friday, May 29 at 11:10 AM")

    def test_human_datetime_returns_invalid_input_unchanged(self) -> None:
        self.assertEqual(human_datetime("not-a-date"), "not-a-date")

    def test_summarize_training_reports_volume_and_long_run_warning(self) -> None:
        summary = summarize_training(
            [
                _run("2026-05-25T06:00:00Z", 3, 140),
                _run("2026-05-27T06:00:00Z", 4, 145),
                _run("2026-05-29T06:00:00Z", 8, 150),
            ],
            days=7,
        )

        self.assertIn("Reviewed 3 runs over the last 7 days.", summary)
        self.assertIn("Total volume: 15.0 mi", summary)
        self.assertIn("Longest run: 8.0 mi", summary)
        self.assertIn("Average HR across HR-tagged runs: 145 bpm.", summary)
        self.assertIn("Watch-out: the long run is a large share", summary)

    def test_summarize_training_handles_no_runs(self) -> None:
        self.assertEqual(summarize_training([], days=14), "No runs found in the last 14 days.")

    def test_summarize_training_handles_missing_heart_rate(self) -> None:
        summary = summarize_training([_run_without_hr("2026-05-29T06:00:00Z", 5)], days=7)

        self.assertIn("No heart-rate data found", summary)


def _run(start_date_local: str, distance_miles: float, average_heartrate: int) -> dict:
    return {
        "type": "Run",
        "start_date_local": start_date_local,
        "distance": distance_miles * METERS_PER_MILE,
        "average_heartrate": average_heartrate,
    }


def _run_without_hr(start_date_local: str, distance_miles: float) -> dict:
    return {
        "type": "Run",
        "start_date_local": start_date_local,
        "distance": distance_miles * METERS_PER_MILE,
    }


if __name__ == "__main__":
    unittest.main()
