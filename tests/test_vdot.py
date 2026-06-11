from __future__ import annotations

import unittest

from running_agent.vdot import race_vdot_context, race_vdot_estimate, vdot_from_performance

METERS_PER_MILE = 1609.344


class VdotTest(unittest.TestCase):
    def test_vdot_from_1959_5k_is_about_50(self) -> None:
        vdot = vdot_from_performance(5000, 19 * 60 + 59)

        self.assertIsNotNone(vdot)
        self.assertAlmostEqual(vdot, 49.9, places=1)

    def test_race_estimate_standardizes_slightly_long_5k(self) -> None:
        estimate = race_vdot_estimate(
            {
                "type": "Run",
                "name": "North Jersey Pride Run",
                "distance": 5068.1,
                "moving_time": 20 * 60 + 2,
                "workout_type": 1,
            }
        )

        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertEqual(estimate.race_label, "5K")
        self.assertAlmostEqual(estimate.vdot, 49.7, places=1)
        self.assertEqual(estimate.table_vdot, 50)

    def test_race_vdot_context_includes_table_paces(self) -> None:
        context = race_vdot_context(
            [
                {
                    "type": "Run",
                    "name": "North Jersey Pride Run",
                    "distance": 5068.1,
                    "moving_time": 20 * 60 + 2,
                    "workout_type": 1,
                }
            ]
        )

        self.assertIn("VDOT 49.7", context)
        self.assertIn("VDOT 50 paces", context)
        self.assertIn("Easy 8:16-9:06/mi", context)
        self.assertIn("Marathon 7:18/mi", context)
        self.assertIn("Threshold 6:52/mi", context)

    def test_non_race_does_not_get_estimate(self) -> None:
        self.assertIsNone(
            race_vdot_estimate(
                {
                    "type": "Run",
                    "name": "Easy Run",
                    "distance": 5 * METERS_PER_MILE,
                    "moving_time": 45 * 60,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
