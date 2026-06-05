from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from running_agent.run_summary import _fallback_summary, run_summary_for_date

METERS_PER_MILE = 1609.344


class RunSummaryTest(unittest.TestCase):
    @patch("running_agent.run_summary.training_goal_context", return_value="Goal")
    @patch("running_agent.run_summary.weekly_plan_context_for_date", return_value="Plan")
    @patch("running_agent.run_summary.coaching_reply", return_value="Nice controlled run.")
    def test_run_summary_returns_natural_coaching_text_without_header(
        self,
        coaching_reply,
        _weekly_plan_context_for_date,
        _training_goal_context,
    ) -> None:
        client = _FakeStravaClient()

        summary = run_summary_for_date(
            client,
            datetime(2026, 5, 29).date(),
        )

        self.assertEqual(summary, "Nice controlled run.")
        self.assertNotIn("Run summary for", summary)

    def test_fallback_summary_includes_error_and_activity_context(self) -> None:
        summary = _fallback_summary(
            {
                "name": "Morning Run",
                "distance": 5 * METERS_PER_MILE,
                "moving_time": 40 * 60,
                "elapsed_time": 42 * 60,
                "start_date_local": "2026-05-29T05:45:00Z",
                "laps": [],
            },
            RuntimeError("model unavailable"),
        )

        self.assertIn("AI coaching was unavailable (model unavailable).", summary)
        self.assertIn("Morning Run: 5.00 mi", summary)
        self.assertIn("No lap-by-lap data", summary)
        self.assertIn("Basic read:", summary)


class _FakeStravaClient:
    def __init__(self):
        self.run = {
            "id": 123,
            "name": "Morning Run",
            "distance": 5 * METERS_PER_MILE,
            "moving_time": 40 * 60,
            "elapsed_time": 42 * 60,
            "start_date_local": "2026-05-29T05:45:00Z",
            "laps": [],
        }

    def runs_on_date(self, _target_date, search_days: int):
        return [self.run]

    def detailed_activity(self, _activity_id: int):
        return self.run

    def recent_activities(self, days: int):
        return [self.run]


if __name__ == "__main__":
    unittest.main()
