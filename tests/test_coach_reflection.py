from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.coach_reflection import (
    _pace_calibration_from_reflection,
    _reflection_without_pace_calibration,
    coach_reflection_context,
    generate_coach_reflection,
    reflection_coach_log_context,
    save_coach_reflection,
)

METERS_PER_MILE = 1609.344


class CoachReflectionTest(unittest.TestCase):
    def test_coach_reflection_context_formats_current_thesis(self) -> None:
        path = _temp_path()

        save_coach_reflection("Current limiter is long-run durability.", path=path)

        context = coach_reflection_context(path=path)
        self.assertIn("Current coach reflection, last updated", context)
        self.assertIn("Current limiter is long-run durability.", context)

    def test_coach_reflection_context_handles_missing_reflection(self) -> None:
        self.assertEqual(
            coach_reflection_context(path=_temp_path()),
            "No coach reflection has been recorded yet.",
        )

    @patch("running_agent.coach_reflection.safe_garmin_weekly_context", return_value="Garmin trend")
    @patch(
        "running_agent.coach_reflection.coach_reflection_context", return_value="Previous thesis"
    )
    @patch("running_agent.coach_reflection.read_coach_log")
    @patch("running_agent.coach_reflection.training_goal_context", return_value="Goal")
    @patch("running_agent.coach_reflection.weekly_plan_context", return_value="Weekly plan")
    @patch("running_agent.coach_reflection.save_pace_calibration")
    @patch("running_agent.coach_reflection.save_coach_reflection")
    @patch(
        "running_agent.openai_client.coaching_reply",
        return_value=(
            "Capacity: Stable.\n\n"
            "Working VDOT/pace calibration: VDOT 50, threshold around 6:55/mi.\n\n"
            "Goal confidence: Moderate.\n\n"
            "Goal requirements/checkpoints: Build durability.\n\n"
            "Current limiter: Long runs.\n\n"
            "Next emphasis: Easy days.\n\n"
            "Watch items: Pace creep."
        ),
    )
    def test_generate_coach_reflection_rewrites_current_thesis(
        self,
        coaching_reply,
        save_coach_reflection,
        save_pace_calibration,
        _weekly_plan_context,
        _training_goal_context,
        read_coach_log,
        _coach_reflection_context,
        _safe_garmin_weekly_context,
    ) -> None:
        read_coach_log.return_value = [
            {
                "type": "run_completed",
                "activity_id": 1,
                "run_date": "2026-06-01",
                "planned_workout": "10 easy",
                "completed_run": "Long Run: 10.00 mi",
            }
        ]
        client = _FakeStravaClient(
            [
                {
                    "type": "Run",
                    "name": "Long Run",
                    "distance": 10 * METERS_PER_MILE,
                    "moving_time": 80 * 60,
                    "start_date_local": "2026-06-01T06:00:00Z",
                }
            ]
        )

        reflection = generate_coach_reflection(client, lookback_days=42)

        self.assertIn("Working VDOT/pace calibration", reflection)
        self.assertEqual(client.requested_days, 42)
        kwargs = coaching_reply.call_args.kwargs
        self.assertIn("Reviewed 1 runs over the last 42 days.", kwargs["training_summary"])
        self.assertIn("Long Run: 10.00 mi", kwargs["recent_runs"])
        self.assertEqual(kwargs["weekly_plan"], "Weekly plan")
        self.assertEqual(kwargs["training_goal"], "Goal")
        self.assertIn("Long Run: 10.00 mi", kwargs["coach_log"])
        self.assertIn("Previous thesis", kwargs["coach_log"])
        self.assertEqual(kwargs["garmin_context"], "Garmin trend")
        self.assertFalse(kwargs["tools_enabled"])
        self.assertFalse(kwargs["include_coach_reflection"])
        self.assertEqual(kwargs["pace_calibration_text"], "No pace calibration has been saved yet.")
        save_coach_reflection.assert_called_once_with(reflection)
        save_pace_calibration.assert_called_once_with("VDOT 50, threshold around 6:55/mi.")

    def test_pace_calibration_from_reflection_extracts_section(self) -> None:
        reflection = "\n".join(
            [
                "Capacity: Stable.",
                "Working VDOT/pace calibration: VDOT 50, confidence medium.",
                "Easy 8:05-8:45/mi; threshold 6:55/mi.",
                "Goal confidence: Moderate.",
            ]
        )

        calibration = _pace_calibration_from_reflection(reflection)

        self.assertEqual(
            calibration,
            "VDOT 50, confidence medium.\nEasy 8:05-8:45/mi; threshold 6:55/mi.",
        )

    def test_reflection_without_pace_calibration_removes_only_pace_section(self) -> None:
        reflection = "\n".join(
            [
                "Capacity: Stable.",
                "Working VDOT/pace calibration: Bad old interval pace.",
                "More stale pace text.",
                "Goal confidence: Moderate.",
            ]
        )

        cleaned = _reflection_without_pace_calibration(reflection)

        self.assertIn("Capacity: Stable.", cleaned)
        self.assertIn("Goal confidence: Moderate.", cleaned)
        self.assertNotIn("Bad old interval pace", cleaned)

    @patch("running_agent.coach_reflection.read_coach_log")
    def test_reflection_coach_log_context_dedupes_runs_and_uses_latest_week_review(
        self,
        read_coach_log,
    ) -> None:
        read_coach_log.return_value = [
            {
                "type": "week_reviewed",
                "week_start": "2026-05-18",
                "week_end": "2026-05-24",
                "summary": "Old review.",
            },
            {
                "type": "run_completed",
                "activity_id": 1,
                "run_date": "2026-05-25",
                "planned_workout": "easy 7",
                "completed_run": "Easy: 7.00 mi",
            },
            {
                "type": "run_completed",
                "activity_id": 1,
                "run_date": "2026-05-25",
                "planned_workout": "easy 7",
                "completed_run": "Easy duplicate: 7.00 mi",
            },
            {
                "type": "week_reviewed",
                "week_start": "2026-05-25",
                "week_end": "2026-05-31",
                "summary": "Latest review.",
            },
        ]

        context = reflection_coach_log_context()

        self.assertIn("Latest review.", context)
        self.assertNotIn("Old review.", context)
        self.assertIn("Easy duplicate: 7.00 mi", context)
        self.assertNotIn("Easy: 7.00 mi", context)


class _FakeStravaClient:
    def __init__(self, activities: list[dict]):
        self.activities = activities
        self.requested_days: int | None = None

    def recent_activities(self, days: int) -> list[dict]:
        self.requested_days = days
        return self.activities


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
