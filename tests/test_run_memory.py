from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from running_agent.run_memory import (
    build_run_memory,
    refresh_run_memory,
    run_memory_context,
    validate_run_memory,
)
from running_agent.strava_store import save_run_detail, save_run_summaries

METERS_PER_MILE = 1609.344


class RunMemoryTest(unittest.TestCase):
    def test_build_run_memory_joins_strava_plan_log_and_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summaries_path = root / "activities.json"
            details_dir = root / "details"
            feedback_path = root / "run_feedback.jsonl"
            coach_log_path = root / "coach_log.jsonl"
            save_run_summaries(
                {
                    "1": _run(
                        1,
                        "Easy Run",
                        "2026-06-18T06:00:00Z",
                        5,
                        average_heartrate=135,
                        max_heartrate=155,
                    ),
                    "2": _run(
                        2,
                        "Workout",
                        "2026-06-19T06:00:00Z",
                        6,
                        average_heartrate=144,
                        max_heartrate=180,
                    ),
                    "3": _run(3, "Old Run", "2026-05-01T06:00:00Z", 4),
                },
                summaries_path,
            )
            save_run_detail(
                {
                    **_run(2, "Workout", "2026-06-19T06:00:00Z", 6),
                    "laps": [
                        {"distance": 400, "moving_time": 95},
                        {"distance": 100, "moving_time": 70},
                        {"distance": 400, "moving_time": 96},
                        {"distance": 100, "moving_time": 75},
                    ],
                },
                details_dir,
            )
            feedback_path.write_text(
                json.dumps(
                    {
                        "type": "post_run_feedback",
                        "activity_id": 2,
                        "run_date": "2026-06-19",
                        "raw": "Felt like 8, heavy legs, no pain",
                        "rpe": 8,
                        "legs": "heavy",
                        "pain": "no",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            coach_log_path.write_text(
                json.dumps(
                    {
                        "type": "run_completed",
                        "activity_id": 2,
                        "run_date": "2026-06-19",
                        "planned_workout": "6 x 400m",
                        "completed_run": "Workout",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = build_run_memory(
                days=14,
                today=date(2026, 6, 19),
                summaries_path=summaries_path,
                details_dir=details_dir,
                feedback_path=feedback_path,
                coach_log_path=coach_log_path,
            )

        self.assertEqual([record["activity_id"] for record in records], [1, 2])
        workout = records[1]
        self.assertEqual(workout["planned_workout"], "6 x 400m")
        self.assertEqual(workout["classification"], "structured workout")
        self.assertEqual(workout["lap_count"], 4)
        self.assertEqual(workout["average_heartrate_percent_max"], 80)
        self.assertEqual(workout["observed_max_heartrate"], 180)
        self.assertEqual(workout["feedback"][0]["rpe"], 8)
        self.assertIn("high_rpe", workout["tags"])
        self.assertIn("leg_fatigue", workout["tags"])
        self.assertNotIn("pain_or_soreness", workout["tags"])

    def test_refresh_run_memory_writes_materialized_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summaries_path = root / "activities.json"
            output_path = root / "run_memory.json"
            save_run_summaries(
                {"1": _run(1, "Easy Run", "2026-06-19T06:00:00Z", 5)}, summaries_path
            )

            data = refresh_run_memory(
                days=7,
                today=date(2026, 6, 19),
                output_path=output_path,
                summaries_path=summaries_path,
                details_dir=root / "details",
                feedback_path=root / "feedback.jsonl",
                coach_log_path=root / "coach_log.jsonl",
            )

            saved = json.loads(output_path.read_text(encoding="utf-8"))
            mode = output_path.stat().st_mode & 0o777

        self.assertEqual(data["lookback_days"], 7)
        self.assertEqual(saved["runs"][0]["activity_id"], 1)
        self.assertEqual(mode, 0o600)

    def test_run_memory_context_formats_latest_records(self) -> None:
        context = run_memory_context(
            [
                {
                    "date": "2026-06-19",
                    "name": "Workout",
                    "distance_miles": 6,
                    "classification": "structured workout",
                    "average_heartrate": 144,
                    "average_heartrate_percent_max": 80,
                    "feedback": [{"rpe": 8, "legs": "heavy", "pain": "no"}],
                    "tags": ["high_rpe", "leg_fatigue"],
                }
            ]
        )

        self.assertIn("Run memory", context)
        self.assertIn("RPE 8", context)
        self.assertIn("avg HR 144 bpm / 80% max HR", context)
        self.assertIn("high_rpe", context)

    def test_validate_run_memory_accepts_feedback_reflected_in_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feedback_path = root / "run_feedback.jsonl"
            feedback_path.write_text(
                json.dumps(
                    {
                        "activity_id": 123,
                        "run_date": "2026-06-19",
                        "created_at": "2026-06-19T12:00:00+00:00",
                        "raw": "RPE 3, no pain",
                        "rpe": 3,
                        "pain": "no",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = validate_run_memory(
                records=[
                    {
                        "activity_id": 123,
                        "date": "2026-06-19",
                        "feedback": [
                            {
                                "created_at": "2026-06-19T12:00:00+00:00",
                                "raw": "RPE 3, no pain",
                                "rpe": 3,
                                "pain": "no",
                            }
                        ],
                    }
                ],
                feedback_path=feedback_path,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["feedback_entries"], 1)

    def test_validate_run_memory_reports_missing_and_stale_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feedback_path = root / "run_feedback.jsonl"
            feedback_path.write_text(
                json.dumps(
                    {
                        "activity_id": 123,
                        "run_date": "2026-06-19",
                        "raw": "RPE 3, no pain",
                        "rpe": 3,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "activity_id": 456,
                        "run_date": "2026-06-20",
                        "raw": "RPE 8, sore",
                        "rpe": 8,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = validate_run_memory(
                records=[
                    {
                        "activity_id": 123,
                        "date": "2026-06-19",
                        "feedback": [{"raw": "RPE 3, no pain"}],
                    }
                ],
                feedback_path=feedback_path,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(len(result["stale_feedback"]), 1)
        self.assertEqual(len(result["missing_feedback"]), 1)


def _run(
    activity_id: int,
    name: str,
    start: str,
    distance_miles: float,
    *,
    average_heartrate: int | None = None,
    max_heartrate: int | None = None,
):
    run = {
        "id": activity_id,
        "name": name,
        "type": "Run",
        "distance": distance_miles * METERS_PER_MILE,
        "moving_time": int(distance_miles * 8 * 60),
        "start_date_local": start,
    }
    if average_heartrate is not None:
        run["average_heartrate"] = average_heartrate
    if max_heartrate is not None:
        run["max_heartrate"] = max_heartrate
    return run


if __name__ == "__main__":
    unittest.main()
