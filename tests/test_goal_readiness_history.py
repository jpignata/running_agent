from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.goal_readiness_history import (
    goal_readiness_history_context,
    load_goal_readiness_history,
    save_goal_readiness_history_entry,
)


class GoalReadinessHistoryTest(unittest.TestCase):
    def test_save_load_and_format_history_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "goal_readiness_history.json"

            entry = save_goal_readiness_history_entry(
                week_start="2026-06-22",
                snapshot={
                    "goal": "Sub-3:10 marathon",
                    "readiness_bucket": "plausible with clear gaps",
                    "main_gap": "Recent volume is still light.",
                    "next_checkpoint": "Consistent mileage week.",
                    "current_anchor": {"distance": "5K", "time": "19:59"},
                    "recent_mileage": {"total_miles": 219.2, "average_weekly_miles": 31.3},
                    "longest_recent_run": "2026-06-21: Long Run, 14.0 mi",
                    "key_workouts": ["2026-06-24: Track, 8.4 mi"],
                    "feedback_risks": [],
                },
                path=path,
            )

            self.assertEqual(entry["week_start"], "2026-06-22")
            self.assertIn("updated_at", entry)
            self.assertEqual(len(load_goal_readiness_history(path)), 1)
            context = goal_readiness_history_context(path)
            self.assertIn("Recent goal readiness history:", context)
            self.assertIn("week 2026-06-22", context)
            self.assertIn("plausible with clear gaps", context)
            self.assertIn("Consistent mileage week.", context)

    def test_save_history_entry_upserts_week(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "goal_readiness_history.json"

            save_goal_readiness_history_entry(
                week_start="2026-06-22",
                snapshot={
                    "readiness_bucket": "building",
                    "main_gap": "Old gap",
                    "next_checkpoint": "Old checkpoint",
                },
                path=path,
            )
            save_goal_readiness_history_entry(
                week_start="2026-06-22",
                snapshot={
                    "readiness_bucket": "plausible with clear gaps",
                    "main_gap": "New gap",
                    "next_checkpoint": "New checkpoint",
                },
                path=path,
            )

            entries = load_goal_readiness_history(path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["readiness_bucket"], "plausible with clear gaps")
            self.assertEqual(entries[0]["main_gap"], "New gap")

    def test_empty_history_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"

            self.assertEqual(
                goal_readiness_history_context(path),
                "No goal readiness history has been recorded yet.",
            )

    def test_empty_week_start_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            save_goal_readiness_history_entry(week_start="", snapshot={})


if __name__ == "__main__":
    unittest.main()
