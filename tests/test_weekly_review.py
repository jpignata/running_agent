from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from running_agent.weekly_review import (
    current_week_start,
    review_week,
    weekly_quality_detail_context,
)

METERS_PER_MILE = 1609.344


class WeeklyReviewTest(unittest.TestCase):
    def test_current_week_start_returns_monday(self) -> None:
        self.assertEqual(current_week_start(datetime(2026, 5, 31).date()).isoformat(), "2026-05-25")

    @patch("running_agent.weekly_review.append_week_review")
    @patch("running_agent.weekly_review.safe_garmin_weekly_context", return_value="Garmin weekly")
    @patch("running_agent.weekly_review.coach_log_context", return_value="Coach log")
    @patch("running_agent.weekly_review.training_goal_context", return_value="Goal")
    @patch("running_agent.weekly_review.weekly_plan_context", return_value="Weekly plan")
    @patch(
        "running_agent.weekly_review.coaching_reply", return_value="Good week. Keep it controlled."
    )
    def test_review_week_passes_context_and_logs_summary(
        self,
        coaching_reply,
        _weekly_plan_context,
        _training_goal_context,
        _coach_log_context,
        _safe_garmin_weekly_context,
        append_week_review,
    ) -> None:
        review = review_week(
            _FakeStravaClient([_run("Easy Run")]),
            week_start=datetime(2026, 5, 25).date(),
        )

        self.assertIn("Weekly review for 2026-05-25 through 2026-05-31:", review)
        self.assertIn("Good week. Keep it controlled.", review)
        prompt = coaching_reply.call_args.args[0]
        kwargs = coaching_reply.call_args.kwargs
        self.assertIn("2026-05-25 through 2026-05-31", prompt)
        self.assertEqual(kwargs["weekly_plan"], "Weekly plan")
        self.assertEqual(kwargs["training_goal"], "Goal")
        self.assertEqual(kwargs["coach_log"], "Coach log")
        self.assertEqual(kwargs["garmin_context"], "Garmin weekly")
        append_week_review.assert_called_once_with(
            week_start="2026-05-25",
            week_end="2026-05-31",
            summary="Good week. Keep it controlled.",
        )

    @patch("running_agent.weekly_review.append_week_review")
    @patch("running_agent.weekly_review.safe_garmin_weekly_context", return_value="Garmin weekly")
    @patch("running_agent.weekly_review.coaching_reply", side_effect=RuntimeError("offline"))
    def test_review_week_has_fallback(self, _coaching_reply, _garmin, append_week_review) -> None:
        review = review_week(
            _FakeStravaClient([_run("Easy Run")]),
            week_start=datetime(2026, 5, 25).date(),
        )

        self.assertIn("AI weekly review was unavailable (offline).", review)
        append_week_review.assert_called_once()

    @patch("running_agent.weekly_review.planned_workout_for_date", return_value="4x1200m + 4x400m")
    def test_weekly_quality_detail_context_fetches_laps_for_planned_workout(
        self, _planned_workout
    ) -> None:
        run = _run("Track")
        run["id"] = 123
        client = _FakeStravaClient([run])
        client.details[123] = {
            **run,
            "laps": [
                {
                    "lap_index": 1,
                    "distance": 0.75 * METERS_PER_MILE,
                    "moving_time": 5 * 60,
                    "elapsed_time": 5 * 60,
                }
            ],
        }

        context = weekly_quality_detail_context(
            client,
            [run],
            week_start=datetime(2026, 5, 25).date(),
            week_end=datetime(2026, 5, 31).date(),
        )

        self.assertIn("Lap data from Strava detailed activity", context)
        self.assertEqual(client.detailed_activity_ids, [123])

    @patch("running_agent.weekly_review.planned_workout_for_date", return_value="easy 5")
    def test_weekly_quality_detail_context_skips_easy_runs(self, _planned_workout) -> None:
        run = _run("Easy Run")
        run["id"] = 123
        client = _FakeStravaClient([run])

        context = weekly_quality_detail_context(
            client,
            [run],
            week_start=datetime(2026, 5, 25).date(),
            week_end=datetime(2026, 5, 31).date(),
        )

        self.assertEqual(context, "")
        self.assertEqual(client.detailed_activity_ids, [])


class _FakeStravaClient:
    def __init__(self, activities: list[dict]):
        self.activities = activities
        self.details: dict[int, dict] = {}
        self.detailed_activity_ids: list[int] = []

    def recent_activities(self, days: int) -> list[dict]:
        return self.activities

    def detailed_activity(self, activity_id: int) -> dict:
        self.detailed_activity_ids.append(activity_id)
        return self.details[activity_id]


def _run(name: str) -> dict:
    return {
        "id": 1,
        "type": "Run",
        "name": name,
        "distance": 5 * METERS_PER_MILE,
        "moving_time": 40 * 60,
        "start_date_local": "2026-05-29T06:00:00Z",
    }


if __name__ == "__main__":
    unittest.main()
