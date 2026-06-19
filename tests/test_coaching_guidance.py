from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.coach_prompt import build_coaching_input
from running_agent.coaching_guidance import (
    DANIELS_TRAINING_RUBRIC,
    RPE_COACHING_RUBRIC,
    coaching_philosophy_context,
)


class CoachingGuidanceTest(unittest.TestCase):
    def test_coaching_philosophy_context_reads_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as handle:
            handle.write("Coaching philosophy:\n- Keep easy days easy.")
            handle.flush()

            context = coaching_philosophy_context(Path(handle.name))

        self.assertEqual(context, "Coaching philosophy:\n- Keep easy days easy.")

    def test_coaching_philosophy_context_handles_missing_file(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "missing-running-agent-philosophy.txt"
        if missing_path.exists():
            missing_path.unlink()

        context = coaching_philosophy_context(missing_path)

        self.assertEqual(context, "No coaching philosophy has been provided.")

    def test_coaching_input_includes_rpe_rubric(self) -> None:
        context = build_coaching_input(
            message="How should I run this threshold workout?",
            training_summary="Recent training.",
            recent_runs="Recent runs.",
            coaching_philosophy_text="Coaching philosophy.",
            athlete_profile_text="Athlete profile.",
            coach_reflection_text="Coach reflection.",
            include_coach_reflection=False,
            pace_calibration_text="Pace calibration.",
            run_memory_text="Run memory context.",
        )

        self.assertIn(RPE_COACHING_RUBRIC, context)
        self.assertIn("Treat reported RPE and feel as core execution evidence", context)
        self.assertIn("Recent run memory:\nRun memory context.", context)

    def test_coaching_input_includes_daniels_training_rubric(self) -> None:
        context = build_coaching_input(
            message="How should I think about my workout paces?",
            training_summary="Recent training.",
            recent_runs="Recent runs.",
            coaching_philosophy_text="Coaching philosophy.",
            athlete_profile_text="Athlete profile.",
            coach_reflection_text="Coach reflection.",
            include_coach_reflection=False,
            pace_calibration_text="Pace calibration.",
            run_memory_text="Run memory context.",
        )

        self.assertIn(DANIELS_TRAINING_RUBRIC, context)
        self.assertIn("Use the working VDOT as a pace governor", context)
        self.assertIn("Prescribe the least intense tool", context)


if __name__ == "__main__":
    unittest.main()
