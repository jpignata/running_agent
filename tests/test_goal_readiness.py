from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from running_agent.goal_readiness import goal_readiness_context, goal_readiness_snapshot
from running_agent.storage import append_jsonl, write_json_file

METERS_PER_MILE = 1609.344


class GoalReadinessTest(unittest.TestCase):
    def test_snapshot_summarizes_goal_evidence_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_json_file(
                paths["goal"],
                {
                    "updated_at": "2026-06-01T12:00:00+00:00",
                    "text": "Sub-19 5K PR this fall",
                },
            )
            write_json_file(
                paths["pace"],
                {
                    "updated_at": "2026-06-01T12:00:00+00:00",
                    "text": "VDOT 51; threshold around 6:44/mi",
                },
            )
            write_json_file(
                paths["race_results"],
                {
                    "results": [
                        {
                            "race_name": "North Jersey 5K",
                            "race_date": "2026-06-07",
                            "distance": "5K",
                            "distance_meters": 5000.0,
                            "time": "19:44",
                            "time_seconds": 1184,
                        }
                    ]
                },
            )
            append_jsonl(
                paths["coach_log"],
                {
                    "type": "run_completed",
                    "run_date": "2026-06-18",
                    "planned_workout": "5 x 1K at 5K rhythm",
                    "completed_run": "Track: 7.0 mi",
                },
            )
            activities = [
                _run("Easy Run", "2026-06-24T06:00:00Z", 6),
                _run("Easy Run", "2026-06-23T06:00:00Z", 6),
                _run("Easy Run", "2026-06-22T06:00:00Z", 6),
                _run("Steady Run", "2026-06-21T06:00:00Z", 8),
                _run("Threshold Workout", "2026-06-20T06:00:00Z", 8),
                _run("Easy Run", "2026-06-18T06:00:00Z", 7),
                _run("Easy Run", "2026-06-17T06:00:00Z", 5),
                _run("Easy Run", "2026-06-16T06:00:00Z", 6),
                _run("Long Run", "2026-06-14T06:00:00Z", 10),
                _run("Easy Run", "2026-06-10T06:00:00Z", 7),
                _run("Easy Run", "2026-06-09T06:00:00Z", 6),
            ]

            snapshot = goal_readiness_snapshot(
                today=date(2026, 6, 24),
                activities=activities,
                goal_path=paths["goal"],
                pace_path=paths["pace"],
                coach_log_path=paths["coach_log"],
                feedback_path=paths["feedback"],
                race_results_path=paths["race_results"],
            )

            self.assertIn("Sub-19 5K", snapshot["goal"])
            self.assertEqual(snapshot["current_anchor"]["source"], "official saved race result")
            self.assertEqual(snapshot["current_anchor"]["distance"], "5K")
            self.assertAlmostEqual(snapshot["current_anchor"]["vdot"], 50.6, places=1)
            self.assertEqual(snapshot["recent_mileage"]["total_miles"], 75.0)
            self.assertIn("Long Run, 10.0 mi", snapshot["longest_recent_run"])
            self.assertTrue(any("Threshold Workout" in item for item in snapshot["key_workouts"]))
            self.assertTrue(any("5 x 1K" in item for item in snapshot["key_workouts"]))
            self.assertEqual(snapshot["readiness_bucket"], "plausible with clear gaps")
            self.assertIn("5 x 1K", snapshot["next_checkpoint"])

            context = goal_readiness_context(snapshot)
            self.assertIn("Goal readiness snapshot:", context)
            self.assertIn("official saved race result", context)
            self.assertIn("VDOT 51", context)

    def test_snapshot_is_too_early_without_goal_or_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))

            snapshot = goal_readiness_snapshot(
                today=date(2026, 6, 24),
                activities=[],
                goal_path=paths["goal"],
                pace_path=paths["pace"],
                coach_log_path=paths["coach_log"],
                feedback_path=paths["feedback"],
                race_results_path=paths["race_results"],
            )

            self.assertIsNone(snapshot["goal"])
            self.assertEqual(snapshot["readiness_bucket"], "too early to judge")
            self.assertIn("No saved goal", snapshot["main_gap"])
            self.assertIn("consistent week", snapshot["next_checkpoint"])

    def test_snapshot_marks_feedback_pain_as_risk_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_json_file(
                paths["goal"],
                {
                    "updated_at": "2026-06-01T12:00:00+00:00",
                    "text": "Sub-40 10K",
                },
            )
            append_jsonl(
                paths["feedback"],
                {
                    "type": "post_run_feedback",
                    "run_date": "2026-06-23",
                    "rpe": 8,
                    "pain": "left calf tight",
                },
            )

            snapshot = goal_readiness_snapshot(
                today=date(2026, 6, 24),
                activities=[_run("Tempo Workout", "2026-06-22T06:00:00Z", 7)],
                goal_path=paths["goal"],
                pace_path=paths["pace"],
                coach_log_path=paths["coach_log"],
                feedback_path=paths["feedback"],
                race_results_path=paths["race_results"],
            )

            self.assertEqual(snapshot["readiness_bucket"], "at risk")
            self.assertIn("pain", snapshot["feedback_risks"][0])
            self.assertIn("pain-free easy run", snapshot["next_checkpoint"])

    def test_snapshot_uses_first_goal_distance_when_secondary_goal_mentions_another_race(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_json_file(
                paths["goal"],
                {
                    "updated_at": "2026-06-01T12:00:00+00:00",
                    "text": (
                        "NYC Marathon on November 1, 2026, target sub-3:10. "
                        "Secondary goal is a half marathon tune-up."
                    ),
                },
            )

            snapshot = goal_readiness_snapshot(
                today=date(2026, 6, 24),
                activities=[_run("Long Run", "2026-06-21T06:00:00Z", 14)],
                goal_path=paths["goal"],
                pace_path=paths["pace"],
                coach_log_path=paths["coach_log"],
                feedback_path=paths["feedback"],
                race_results_path=paths["race_results"],
            )

            self.assertIn("distance signal: marathon", snapshot["goal"])
            self.assertIn("performance anchor", snapshot["next_checkpoint"])

    def test_marathon_checkpoint_prioritizes_durability_before_marathon_pace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_json_file(
                paths["goal"],
                {
                    "updated_at": "2026-06-01T12:00:00+00:00",
                    "text": "NYC Marathon on November 1, 2026, target sub-3:10.",
                },
            )
            write_json_file(
                paths["race_results"],
                {
                    "results": [
                        {
                            "race_name": "North Jersey 5K",
                            "race_date": "2026-06-07",
                            "distance": "5K",
                            "distance_meters": 5000.0,
                            "time": "19:59",
                            "time_seconds": 1199,
                        }
                    ]
                },
            )
            activities = [
                _run("Easy Run", "2026-06-24T06:00:00Z", 6),
                _run("Track Workout", "2026-06-22T06:00:00Z", 7),
                _run("Long Run", "2026-06-21T06:00:00Z", 12),
                _run("Easy Run", "2026-06-19T06:00:00Z", 6),
                _run("Easy Run", "2026-06-18T06:00:00Z", 6),
                _run("Easy Run", "2026-06-17T06:00:00Z", 5),
                _run("Easy Run", "2026-06-16T06:00:00Z", 5),
                _run("Easy Run", "2026-06-13T06:00:00Z", 8),
                _run("Steady Run", "2026-06-12T06:00:00Z", 8),
                _run("Easy Run", "2026-06-11T06:00:00Z", 7),
                _run("Easy Run", "2026-06-10T06:00:00Z", 7),
                _run("Medium Easy Run", "2026-06-14T06:00:00Z", 10),
                _run("Easy Run", "2026-06-09T06:00:00Z", 9),
                _run("Recovery Run", "2026-06-08T06:00:00Z", 9),
            ]

            snapshot = goal_readiness_snapshot(
                today=date(2026, 6, 24),
                activities=activities,
                goal_path=paths["goal"],
                pace_path=paths["pace"],
                coach_log_path=paths["coach_log"],
                feedback_path=paths["feedback"],
                race_results_path=paths["race_results"],
            )

            self.assertIn("Long-run durability", snapshot["main_gap"])
            self.assertIn("Controlled long run progression", snapshot["next_checkpoint"])
            self.assertIn("before adding marathon-pace segments", snapshot["next_checkpoint"])

    def test_5k_checkpoint_prioritizes_pace_tolerance_when_volume_and_workouts_exist(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_json_file(
                paths["goal"],
                {
                    "updated_at": "2026-06-01T12:00:00+00:00",
                    "text": "Sub-19 5K PR this fall",
                },
            )
            write_json_file(
                paths["race_results"],
                {
                    "results": [
                        {
                            "race_name": "North Jersey 5K",
                            "race_date": "2026-06-07",
                            "distance": "5K",
                            "distance_meters": 5000.0,
                            "time": "19:44",
                            "time_seconds": 1184,
                        }
                    ]
                },
            )
            activities = [
                _run("Easy Run", "2026-06-24T06:00:00Z", 6),
                _run("Threshold Workout", "2026-06-22T06:00:00Z", 7),
                _run("Long Run", "2026-06-21T06:00:00Z", 8),
                _run("Easy Run", "2026-06-20T06:00:00Z", 4),
                _run("Easy Run", "2026-06-19T06:00:00Z", 6),
                _run("Easy Run", "2026-06-18T06:00:00Z", 5),
                _run("Easy Run", "2026-06-17T06:00:00Z", 5),
            ]

            snapshot = goal_readiness_snapshot(
                today=date(2026, 6, 24),
                activities=activities,
                goal_path=paths["goal"],
                pace_path=paths["pace"],
                coach_log_path=paths["coach_log"],
                feedback_path=paths["feedback"],
                race_results_path=paths["race_results"],
            )

            self.assertIn("5K pace tolerance", snapshot["main_gap"])
            self.assertIn("5 x 1K", snapshot["next_checkpoint"])


def _paths(root: Path) -> dict[str, Path]:
    return {
        "goal": root / "training_goal.json",
        "pace": root / "pace_calibration.json",
        "coach_log": root / "coach_log.jsonl",
        "feedback": root / "run_feedback.jsonl",
        "race_results": root / "race_results.json",
    }


def _run(name: str, start_date_local: str, distance_miles: float) -> dict:
    return {
        "id": abs(hash((name, start_date_local))) % 100000,
        "type": "Run",
        "name": name,
        "distance": distance_miles * METERS_PER_MILE,
        "moving_time": int(distance_miles * 8 * 60),
        "start_date": start_date_local,
        "start_date_local": start_date_local,
    }


if __name__ == "__main__":
    unittest.main()
