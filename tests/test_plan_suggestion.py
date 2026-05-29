from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from running_agent.plan_suggestion import (
    PLAN_STATE_KEY,
    mark_sunday_plan_sent,
    next_week_start,
    should_send_sunday_plan,
    suggest_next_week_plan,
)

METERS_PER_MILE = 1609.344


class PlanSuggestionTest(unittest.TestCase):
    def test_sunday_plan_trigger_only_after_sunday_evening_once_per_week(self) -> None:
        state: dict[str, str] = {}
        sunday_afternoon = datetime(2026, 5, 31, 17, 59, tzinfo=timezone.utc)
        sunday_evening = datetime(2026, 5, 31, 18, 0, tzinfo=timezone.utc)

        self.assertFalse(should_send_sunday_plan(sunday_afternoon, state))
        self.assertTrue(should_send_sunday_plan(sunday_evening, state))

        mark_sunday_plan_sent(sunday_evening, state)

        self.assertEqual(state[PLAN_STATE_KEY], "2026-06-01")
        self.assertFalse(should_send_sunday_plan(sunday_evening, state))

    def test_next_week_start_returns_following_monday(self) -> None:
        self.assertEqual(next_week_start(datetime(2026, 5, 31).date()).isoformat(), "2026-06-01")
        self.assertEqual(next_week_start(datetime(2026, 6, 1).date()).isoformat(), "2026-06-08")

    @patch("running_agent.plan_suggestion.training_goal_context", return_value="Goal context")
    @patch("running_agent.plan_suggestion.weekly_plan_context", return_value="Weekly context")
    @patch(
        "running_agent.plan_suggestion.coaching_reply",
        return_value="Monday: Easy\nTuesday: Workout",
    )
    def test_suggest_next_week_plan_uses_recent_training_context(
        self,
        coaching_reply,
        _weekly_plan_context,
        _training_goal_context,
    ) -> None:
        client = _FakeStravaClient(
            [
                {
                    "type": "Run",
                    "name": "Easy Run",
                    "distance": 5 * METERS_PER_MILE,
                    "moving_time": 40 * 60,
                    "start_date_local": "2026-05-29T06:00:00Z",
                }
            ]
        )

        plan = suggest_next_week_plan(
            client,
            target_week_start=datetime(2026, 6, 1).date(),
            lookback_days=42,
        )

        self.assertIn("Next week plan idea for 2026-06-01:", plan)
        self.assertIn("Monday: Easy", plan)
        self.assertEqual(client.requested_days, 42)
        kwargs = coaching_reply.call_args.kwargs
        prompt = coaching_reply.call_args.args[0]
        self.assertIn("2026-06-01 through 2026-06-07", prompt)
        self.assertIn("current or just-finished plan", prompt)
        self.assertIn("Do not copy it forward", prompt)
        self.assertIn("Reviewed 1 runs over the last 42 days.", kwargs["training_summary"])
        self.assertIn("Easy Run: 5.00 mi", kwargs["recent_runs"])
        self.assertEqual(kwargs["weekly_plan"], "Weekly context")
        self.assertEqual(kwargs["training_goal"], "Goal context")

    @patch("running_agent.plan_suggestion.training_goal_context", return_value="Goal context")
    @patch("running_agent.plan_suggestion.weekly_plan_context", return_value="Weekly context")
    @patch("running_agent.plan_suggestion.coaching_reply", side_effect=RuntimeError("offline"))
    def test_suggest_next_week_plan_has_offline_fallback(
        self,
        _coaching_reply,
        _weekly_plan_context,
        _training_goal_context,
    ) -> None:
        plan = suggest_next_week_plan(
            _FakeStravaClient([]),
            target_week_start=datetime(2026, 6, 1).date(),
        )

        self.assertIn("AI planning was unavailable (offline).", plan)
        self.assertIn("Monday: Rest", plan)
        self.assertIn("Saturday: Long run", plan)


class _FakeStravaClient:
    def __init__(self, activities: list[dict]):
        self.activities = activities
        self.requested_days: int | None = None

    def recent_activities(self, days: int) -> list[dict]:
        self.requested_days = days
        return self.activities


if __name__ == "__main__":
    unittest.main()
