from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from running_agent.coach_time import COACH_TIME_ZONE
from running_agent.plan_store import (
    parse_weekly_plan,
    planned_workout_for_date,
    upcoming_plan_context_after_date,
    update_weekly_plan_days,
    weekly_plan_context,
    weekly_plan_context_for_date,
    weekly_plan_context_for_week,
)


class PlanStoreTest(unittest.TestCase):
    def test_parse_weekly_plan_accepts_common_weekday_forms(self) -> None:
        parsed = parse_weekly_plan(
            "\n".join(
                [
                    "Mon easy 7",
                    "Tuesday: easy 6 with strides",
                    "Wed - 4x1200m",
                    "Fri, easy 6",
                    "Saturday long 14",
                ]
            )
        )

        self.assertEqual(parsed["Monday"], "easy 7")
        self.assertEqual(parsed["Tuesday"], "easy 6 with strides")
        self.assertEqual(parsed["Wednesday"], "4x1200m")
        self.assertEqual(parsed["Friday"], "easy 6")
        self.assertEqual(parsed["Saturday"], "long 14")

    def test_planned_workout_for_date_returns_matching_weekday(self) -> None:
        path = _plan_file("Monday easy 7\nFriday easy 6")

        self.assertEqual(planned_workout_for_date(date(2026, 5, 29), path), "easy 6")

    def test_weekly_plan_context_for_date_prioritizes_matched_day(self) -> None:
        path = _plan_file("Monday easy 7\nFriday easy 6")

        context = weekly_plan_context_for_date(date(2026, 5, 29), path)

        self.assertIn("Run date: Friday, May 29", context)
        self.assertIn("Matched plan day: Friday", context)
        self.assertIn("Planned workout for Friday: easy 6", context)
        self.assertIn("Full weekly plan:", context)

    def test_upcoming_plan_context_after_date_lists_remaining_week(self) -> None:
        path = _plan_file(
            "\n".join(
                [
                    "Monday easy 6",
                    "Wednesday 6x800m",
                    "Saturday easy 4",
                    "Sunday 5K race",
                ]
            )
        )

        context = upcoming_plan_context_after_date(date(2026, 6, 3), path)

        self.assertIn("Remaining plan after Wednesday, Jun 3", context)
        self.assertNotIn("Monday easy 6", context)
        self.assertNotIn("Wednesday 6x800m", context)
        self.assertIn("Saturday: easy 4", context)
        self.assertIn("Sunday: 5K race", context)

    def test_update_weekly_plan_days_preserves_existing_days_and_adds_missing_day(self) -> None:
        path = _plan_file(
            "Monday rest\n"
            "Tuesday 5 miles\n"
            "Wednesday workout\n"
            "Thursday rest\n"
            "Friday 4 miles\n"
            "Saturday 10 miles"
        )

        result = update_weekly_plan_days({"Saturday": "rest", "Sunday": "10 miles"}, path)

        self.assertEqual(
            result["text"],
            "Monday rest\n"
            "Tuesday 5 miles\n"
            "Wednesday workout\n"
            "Thursday rest\n"
            "Friday 4 miles\n"
            "Saturday rest\n"
            "Sunday 10 miles",
        )

    @patch("running_agent.plan_store.coach_today", return_value=date(2026, 6, 14))
    def test_weekly_plan_context_describes_next_week_naturally(self, _coach_today) -> None:
        path = _plan_file("Monday 5 easy", week_start="2026-06-15")

        context = weekly_plan_context(path)

        self.assertIn("Weekly plan for next week", context)
        self.assertNotIn("week starting 2026-06-15", context)

    @patch("running_agent.plan_store.coach_today", return_value=date(2026, 6, 17))
    def test_weekly_plan_context_describes_this_week_naturally(self, _coach_today) -> None:
        path = _plan_file("Monday 5 easy", week_start="2026-06-15")

        context = weekly_plan_context(path)

        self.assertIn("Weekly plan for this week", context)

    @patch("running_agent.plan_store.coach_today", return_value=date(2026, 6, 30))
    def test_weekly_plan_context_uses_short_date_for_other_weeks(self, _coach_today) -> None:
        path = _plan_file("Monday 5 easy", week_start="2026-06-15")

        context = weekly_plan_context(path)

        self.assertIn("Weekly plan for week of 6/15", context)

    @patch(
        "running_agent.time_format.coach_now",
        return_value=datetime(2026, 6, 14, 16, 30, tzinfo=COACH_TIME_ZONE),
    )
    @patch("running_agent.plan_store.coach_today", return_value=date(2026, 6, 14))
    def test_weekly_plan_context_uses_relative_coach_time_timestamp(
        self, _coach_today, _coach_now
    ) -> None:
        path = _plan_file(
            "Monday easy 6",
            week_start="2026-06-15",
            updated_at="2026-06-14T20:10:00+00:00",
        )

        context = weekly_plan_context(path)

        self.assertIn("Weekly plan for next week", context)
        self.assertIn("last updated 20 minutes ago", context)
        self.assertNotIn("8:10 PM", context)

    @patch("running_agent.plan_store.coach_today", return_value=date(2026, 6, 14))
    def test_weekly_plan_context_for_week_requires_matching_week_start(self, _coach_today) -> None:
        path = _plan_file("Monday 5 easy", week_start="2026-06-15")

        matching = weekly_plan_context_for_week(date(2026, 6, 15), path)
        missing = weekly_plan_context_for_week(date(2026, 6, 22), path)

        self.assertIn("Saved weekly plan for next week", matching)
        self.assertIn("Monday 5 easy", matching)
        self.assertIn("No saved weekly plan explicitly applies", missing)


def _plan_file(
    text: str,
    week_start: str | None = None,
    updated_at: str = "2026-05-29T15:10:00+00:00",
) -> Path:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    path = Path(handle.name)
    with handle:
        data = {"updated_at": updated_at, "text": text}
        if week_start:
            data["week_start"] = week_start
        json.dump(data, handle)
    return path


if __name__ == "__main__":
    unittest.main()
