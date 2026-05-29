from __future__ import annotations

import unittest

from running_agent.feedback import summarize_training
from running_agent.time_format import human_datetime

METERS_PER_MILE = 1609.344


class FeedbackAndTimeTest(unittest.TestCase):
    def test_human_datetime_formats_iso_timestamp(self) -> None:
        formatted = human_datetime("2026-05-29T15:10:00+00:00")

        self.assertIn("Friday, May 29", formatted)

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
