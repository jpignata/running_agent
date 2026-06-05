from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from running_agent.evening_report import (
    EVENING_REPORT_STATE_KEY,
    end_of_day_report,
    mark_evening_report_sent,
    should_send_evening_report,
)

METERS_PER_MILE = 1609.344


class EveningReportTest(unittest.TestCase):
    def test_evening_report_trigger_only_after_830_once_per_day(self) -> None:
        state: dict[str, str] = {}
        before = datetime(2026, 6, 2, 0, 29, tzinfo=timezone.utc)
        at_time = datetime(2026, 6, 2, 0, 30, tzinfo=timezone.utc)

        self.assertFalse(should_send_evening_report(before, state))
        self.assertTrue(should_send_evening_report(at_time, state))

        mark_evening_report_sent(at_time, state)

        self.assertEqual(state[EVENING_REPORT_STATE_KEY], "2026-06-01")
        self.assertFalse(should_send_evening_report(at_time, state))

    def test_evening_report_trigger_uses_est_in_winter(self) -> None:
        state: dict[str, str] = {}
        before = datetime(2026, 1, 4, 1, 29, tzinfo=timezone.utc)
        at_time = datetime(2026, 1, 4, 1, 30, tzinfo=timezone.utc)

        self.assertFalse(should_send_evening_report(before, state))
        self.assertTrue(should_send_evening_report(at_time, state))

    def test_evening_report_skips_sundays(self) -> None:
        state: dict[str, str] = {}
        sunday_evening = datetime(2026, 6, 8, 0, 30, tzinfo=timezone.utc)

        self.assertFalse(should_send_evening_report(sunday_evening, state))

    @patch("running_agent.evening_report.coach_log_context", return_value="Coach log context")
    @patch("running_agent.evening_report.training_goal_context", return_value="Goal context")
    @patch(
        "running_agent.evening_report.upcoming_plan_context_after_date",
        return_value="Remaining plan after Wednesday, Jun 3:\nSunday: 5K race",
    )
    @patch(
        "running_agent.evening_report.weekly_plan_context_for_date",
        return_value="Matched plan for today",
    )
    @patch("running_agent.evening_report.coaching_reply", return_value="Good day. Sleep well.")
    def test_end_of_day_report_passes_today_context_to_model(
        self,
        coaching_reply,
        _weekly_plan_context_for_date,
        _upcoming_plan_context_after_date,
        _training_goal_context,
        _coach_log_context,
    ) -> None:
        run = {
            "type": "Run",
            "name": "Track",
            "distance": 7 * METERS_PER_MILE,
            "moving_time": 56 * 60,
            "start_date_local": "2026-06-03T06:00:00Z",
        }
        client = _FakeStravaClient([run])
        client.runs_by_date["2026-06-03"] = [run]

        report = end_of_day_report(
            client,
            target_date=datetime(2026, 6, 3).date(),
            garmin_context_provider=lambda: "Garmin readiness context",
        )

        self.assertEqual(report, "Good day. Sleep well.")
        self.assertEqual(client.requested_days, 7)
        self.assertEqual(client.search_days, 3)
        kwargs = coaching_reply.call_args.kwargs
        self.assertIn("Track: 7.00 mi", kwargs["recent_runs"])
        self.assertIn("Matched plan for today", kwargs["weekly_plan"])
        self.assertIn("Sunday: 5K race", kwargs["weekly_plan"])
        self.assertEqual(kwargs["training_goal"], "Goal context")
        self.assertEqual(kwargs["coach_log"], "Coach log context")
        self.assertEqual(kwargs["garmin_context"], "Garmin readiness context")
        self.assertFalse(kwargs["tools_enabled"])
        self.assertEqual(kwargs["max_output_tokens"], 220)

    @patch("running_agent.evening_report.coach_log_context", return_value="Coach log context")
    @patch("running_agent.evening_report.training_goal_context", return_value="Goal context")
    @patch(
        "running_agent.evening_report.upcoming_plan_context_after_date",
        return_value="Remaining plan after Tuesday, Jun 2:\nSunday: 5K race",
    )
    @patch(
        "running_agent.evening_report.weekly_plan_context_for_date",
        return_value="Matched plan for report date",
    )
    @patch("running_agent.evening_report.coaching_reply", return_value="Good day. Sleep well.")
    def test_end_of_day_report_excludes_activities_after_target_date(
        self,
        coaching_reply,
        _weekly_plan_context_for_date,
        _upcoming_plan_context_after_date,
        _training_goal_context,
        _coach_log_context,
    ) -> None:
        yesterday = {
            "type": "Run",
            "name": "Easy",
            "distance": 5 * METERS_PER_MILE,
            "moving_time": 45 * 60,
            "start_date_local": "2026-06-02T06:00:00Z",
        }
        today = {
            "type": "Run",
            "name": "Track",
            "distance": 7 * METERS_PER_MILE,
            "moving_time": 56 * 60,
            "start_date_local": "2026-06-03T06:00:00Z",
        }
        client = _FakeStravaClient([today, yesterday])
        client.runs_by_date["2026-06-02"] = [yesterday]

        end_of_day_report(
            client,
            target_date=datetime(2026, 6, 2).date(),
            garmin_context_provider=lambda: "Garmin readiness context",
        )

        kwargs = coaching_reply.call_args.kwargs
        self.assertIn("Reviewed 1 runs", kwargs["training_summary"])
        self.assertIn("2026-06-02T06:00:00Z", kwargs["training_summary"])
        self.assertNotIn("2026-06-03T06:00:00Z", kwargs["training_summary"])
        self.assertIn("Easy: 5.00 mi", kwargs["recent_runs"])
        self.assertNotIn("Track", kwargs["recent_runs"])

    @patch(
        "running_agent.evening_report.weekly_plan_context_for_date",
        return_value="Matched plan for today",
    )
    @patch("running_agent.evening_report.coaching_reply", side_effect=RuntimeError("offline"))
    def test_end_of_day_report_has_fallback(self, _coaching_reply, _weekly_plan) -> None:
        report = end_of_day_report(
            _FakeStravaClient([]),
            target_date=datetime(2026, 6, 3).date(),
            garmin_context_provider=lambda: "Garmin readiness context",
        )

        self.assertIn("AI end-of-day report was unavailable (offline).", report)
        self.assertIn("No Strava runs completed on 2026-06-03.", report)
        self.assertIn("Garmin readiness context", report)


class _FakeStravaClient:
    def __init__(self, activities: list[dict]):
        self.activities = activities
        self.requested_days: int | None = None
        self.runs_by_date: dict[str, list[dict]] = {}
        self.search_days: int | None = None

    def recent_activities(self, days: int) -> list[dict]:
        self.requested_days = days
        return self.activities

    def runs_on_date(self, target_date, search_days: int) -> list[dict]:
        self.search_days = search_days
        return self.runs_by_date.get(target_date.isoformat(), [])


if __name__ == "__main__":
    unittest.main()
