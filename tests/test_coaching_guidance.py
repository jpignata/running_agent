from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.coach_prompt import COACHING_INSTRUCTIONS, build_coaching_input
from running_agent.coaching_guidance import (
    DANIELS_TRAINING_RUBRIC,
    GARMIN_COACHING_RUBRIC,
    PROMPT_COACHING_PHILOSOPHY,
    RPE_COACHING_RUBRIC,
    TRAINING_PROGRESSION_RUBRIC,
    coaching_philosophy_context,
)


class CoachingGuidanceTest(unittest.TestCase):
    def test_return_guidance_is_present_with_old_fitness_and_no_recent_runs(self) -> None:
        context = build_coaching_input(
            message="I restarted Saturday after an injury. My ankle is still faintly sore.",
            training_summary="No recent synced runs.",
            recent_runs="No runs available.",
            athlete_profile_text="Prefer to keep quality work.",
            coach_reflection_text="Build marathon long runs.",
            pace_calibration_text="VDOT 50 from a pre-break race.",
            run_memory_text="Historical runs.",
        )

        self.assertIn(TRAINING_PROGRESSION_RUBRIC, context)
        self.assertIn("Return-from-injury guidance takes precedence", context)
        self.assertIn("Residual pain is not proof of recovery", context)
        self.assertIn("not a zero-mile week or a partial restart week", context)
        self.assertIn("Do not invent a detraining percentage", context)
        self.assertIn("infer an injury from missing synced runs alone", context)
        self.assertIn("Apply the return-from-injury guidance", COACHING_INSTRUCTIONS)

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

    def test_coaching_input_uses_compact_prompt_philosophy_by_default(self) -> None:
        context = build_coaching_input(
            message="How should I run today?",
            training_summary="Recent training.",
            recent_runs="Recent runs.",
            athlete_profile_text="Athlete profile.",
            coach_reflection_text="Coach reflection.",
            include_coach_reflection=False,
            pace_calibration_text="Pace calibration.",
            run_memory_text="Run memory context.",
        )

        self.assertIn(PROMPT_COACHING_PHILOSOPHY, context)
        self.assertIn("Maintain a working VDOT", context)
        self.assertLess(len(PROMPT_COACHING_PHILOSOPHY), len(coaching_philosophy_context()))

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

    def test_coaching_input_demotes_body_battery(self) -> None:
        context = build_coaching_input(
            message="How does Garmin look today?",
            training_summary="Recent training.",
            recent_runs="Recent runs.",
            coaching_philosophy_text="Coaching philosophy.",
            athlete_profile_text="Athlete profile.",
            coach_reflection_text="Coach reflection.",
            include_coach_reflection=False,
            pace_calibration_text="Pace calibration.",
            run_memory_text="Run memory context.",
        )

        self.assertIn(GARMIN_COACHING_RUBRIC, context)
        self.assertIn("Treat Body Battery as a soft composite", context)
        self.assertIn("Do not double-count it as independent evidence", context)
        self.assertIn("Mention Body Battery only when the athlete asks", context)

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

    def test_coaching_input_includes_goal_readiness_snapshot(self) -> None:
        context = build_coaching_input(
            message="Am I on track?",
            training_summary="Recent training.",
            recent_runs="Recent runs.",
            goal_readiness="Readiness bucket: building",
            coaching_philosophy_text="Coaching philosophy.",
            athlete_profile_text="Athlete profile.",
            coach_reflection_text="Coach reflection.",
            include_coach_reflection=False,
            pace_calibration_text="Pace calibration.",
            run_memory_text="Run memory context.",
        )

        self.assertIn("Deterministic goal-readiness snapshot:", context)
        self.assertIn("Readiness bucket: building", context)
        self.assertIn("When the athlete asks a goal-readiness question", COACHING_INSTRUCTIONS)
        self.assertIn("Answer with concrete evidence", COACHING_INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
