from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from running_agent.scheduled_preview import (
    format_scheduled_preview,
    preview_scheduled_message,
)


class ScheduledPreviewTest(unittest.TestCase):
    @patch("running_agent.scheduled_preview.daily_workout_checkin", return_value="Morning note")
    @patch("running_agent.scheduled_preview.has_completed_run_for_date", return_value=False)
    @patch("running_agent.scheduled_preview.has_planned_workout_for_date", return_value=True)
    def test_preview_morning_generates_without_mutating_state(
        self,
        has_planned_workout_for_date,
        has_completed_run_for_date,
        daily_workout_checkin,
    ) -> None:
        state = {}
        client = _FakeStrava()
        target_date = date(2026, 6, 5)

        preview = preview_scheduled_message(
            "morning",
            client=client,
            target_date=target_date,
            state=state,
        )

        self.assertTrue(preview.would_send)
        self.assertEqual(preview.message, "Morning note")
        self.assertFalse(preview.tools_enabled)
        self.assertEqual(state, {})
        has_planned_workout_for_date.assert_called_once_with(target_date)
        has_completed_run_for_date.assert_called_once_with(client, target_date)
        daily_workout_checkin.assert_called_once_with(
            client,
            target_date=target_date,
            lookback_days=7,
        )

    @patch("running_agent.scheduled_preview.end_of_day_report", return_value="Evening note")
    @patch("running_agent.scheduled_preview.has_completed_run_for_date", return_value=False)
    def test_preview_evening_reports_scheduler_skip_reasons(
        self,
        has_completed_run_for_date,
        end_of_day_report,
    ) -> None:
        state = {"last_evening_report_date": "2026-06-07"}
        client = _FakeStrava()
        target_date = date(2026, 6, 7)

        preview = preview_scheduled_message(
            "evening",
            client=client,
            target_date=target_date,
            state=state,
        )

        self.assertFalse(preview.would_send)
        self.assertEqual(
            preview.skip_reasons,
            [
                "Sunday evening report suppressed",
                "already sent for date",
                "no completed run for date",
            ],
        )
        self.assertEqual(preview.message, "Evening note")
        has_completed_run_for_date.assert_called_once_with(client, target_date)
        end_of_day_report.assert_called_once_with(
            client,
            target_date=target_date,
            lookback_days=7,
        )

    @patch(
        "running_agent.scheduled_preview.weekly_coaching_message",
        return_value="Weekly note",
    )
    def test_preview_weekly_uses_sunday_generation_path_without_logging_review(
        self,
        weekly_coaching_message,
    ) -> None:
        client = _FakeStrava()

        preview = preview_scheduled_message(
            "weekly",
            client=client,
            target_date=date(2026, 6, 7),
            state={},
        )

        self.assertTrue(preview.would_send)
        self.assertEqual(preview.message, "Weekly note")
        weekly_coaching_message.assert_called_once_with(
            client,
            week_start=date(2026, 6, 1),
            target_week_start=date(2026, 6, 8),
            lookback_days=42,
            log_review=False,
        )

    @patch(
        "running_agent.scheduled_preview.weekly_coaching_message",
        return_value="Weekly note",
    )
    def test_preview_weekly_reports_non_sunday_skip_reason(
        self,
        _weekly_coaching_message,
    ) -> None:
        preview = preview_scheduled_message(
            "weekly",
            client=_FakeStrava(),
            target_date=date(2026, 6, 5),
            state={},
        )

        self.assertFalse(preview.would_send)
        self.assertEqual(preview.skip_reasons, ["not Sunday"])

    @patch("running_agent.scheduled_preview.daily_workout_checkin", return_value="Morning note")
    @patch("running_agent.scheduled_preview.has_completed_run_for_date", return_value=False)
    @patch("running_agent.scheduled_preview.has_planned_workout_for_date", return_value=True)
    def test_format_scheduled_preview_includes_metadata_and_message(
        self,
        _has_planned_workout_for_date,
        _has_completed_run_for_date,
        _daily_workout_checkin,
    ) -> None:
        preview = preview_scheduled_message(
            "morning",
            client=_FakeStrava(),
            target_date=date(2026, 6, 5),
            state={},
        )

        text = format_scheduled_preview(preview)

        self.assertIn("Scheduled message preview", text)
        self.assertIn("Kind: morning", text)
        self.assertIn("Would normally send: yes", text)
        self.assertIn("Tools enabled: no", text)
        self.assertIn("Message:\n\nMorning note", text)


class _FakeStrava:
    pass


if __name__ == "__main__":
    unittest.main()
