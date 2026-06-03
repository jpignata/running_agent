from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from running_agent.plan_store import (
    parse_weekly_plan,
    planned_workout_for_date,
    upcoming_plan_context_after_date,
    weekly_plan_context_for_date,
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


def _plan_file(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    path = Path(handle.name)
    with handle:
        json.dump({"updated_at": "2026-05-29T15:10:00+00:00", "text": text}, handle)
    return path


if __name__ == "__main__":
    unittest.main()
