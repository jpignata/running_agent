from __future__ import annotations

import unittest

from running_agent.workout_classifier import classify_workout

METERS_PER_MILE = 1609.344


class WorkoutClassifierTest(unittest.TestCase):
    def test_plan_race_overrides_generic_activity_name(self) -> None:
        activity = _activity(distance_miles=3.12, moving_time=20 * 60, laps=[])

        classification, reason, emphasis = classify_workout(activity, "Saturday 5K race")

        self.assertEqual(classification, "race")
        self.assertIn("race", reason)
        self.assertIn("race execution", emphasis)

    def test_plan_interval_structure_classifies_as_structured_workout(self) -> None:
        activity = _activity(distance_miles=8, moving_time=70 * 60, laps=[])

        classification, reason, emphasis = classify_workout(
            activity,
            "2mi WU, 4x1200m at 6:25-6:35/mi with 3 mins rest, 4x400m, CD",
        )

        self.assertEqual(classification, "structured workout")
        self.assertIn("weekly plan", reason)
        self.assertIn("reps", emphasis)

    def test_plan_long_run_classifies_as_long_run(self) -> None:
        activity = _activity(distance_miles=8, moving_time=70 * 60, laps=[])

        classification, reason, emphasis = classify_workout(activity, "Sunday long 14")

        self.assertEqual(classification, "long run")
        self.assertIn("long run", reason)
        self.assertIn("fueling", emphasis)

    def test_lap_pattern_classifies_as_structured_without_plan(self) -> None:
        activity = _activity(
            distance_miles=7,
            moving_time=60 * 60,
            laps=[
                _lap(distance_miles=0.75, moving_time=4 * 60 + 55),
                _lap(distance_miles=0.08, moving_time=3 * 60),
                _lap(distance_miles=0.75, moving_time=4 * 60 + 56),
                _lap(distance_miles=0.08, moving_time=3 * 60),
            ],
        )

        classification, reason, emphasis = classify_workout(activity)

        self.assertEqual(classification, "structured workout")
        self.assertIn("quality-looking", reason)
        self.assertIn("lap structure", emphasis)

    def test_easy_plan_wins_when_no_strong_actual_signal(self) -> None:
        activity = _activity(distance_miles=6, moving_time=50 * 60, laps=[])

        classification, reason, emphasis = classify_workout(activity, "Friday easy 6")

        self.assertEqual(classification, "easy run")
        self.assertIn("easy", reason)
        self.assertIn("avoid over-analyzing", emphasis)

    def test_distance_fallback_classifies_long_run(self) -> None:
        activity = _activity(distance_miles=12, moving_time=95 * 60, laps=[])

        classification, reason, emphasis = classify_workout(activity)

        self.assertEqual(classification, "long run")
        self.assertIn("long-run sized", reason)
        self.assertIn("aerobic durability", emphasis)


def _activity(
    distance_miles: float,
    moving_time: int,
    laps: list[dict] | None = None,
) -> dict:
    return {
        "distance": distance_miles * METERS_PER_MILE,
        "moving_time": moving_time,
        "laps": laps or [],
    }


def _lap(distance_miles: float, moving_time: int) -> dict:
    return {
        "distance": distance_miles * METERS_PER_MILE,
        "moving_time": moving_time,
    }


if __name__ == "__main__":
    unittest.main()
