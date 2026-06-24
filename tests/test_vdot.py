from __future__ import annotations

import unittest
from unittest.mock import patch

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
        self.assertEqual(estimate.source, "full activity")

    def test_race_estimate_prefers_standard_distance_best_effort(self) -> None:
        estimate = race_vdot_estimate(
            {
                "type": "Run",
                "name": "North Jersey Pride Run",
                "distance": 5068.1,
                "moving_time": 20 * 60 + 2,
                "workout_type": 1,
                "best_efforts": [
                    {
                        "name": "5K",
                        "distance": 5000,
                        "moving_time": 19 * 60 + 59,
                    }
                ],
            }
        )

        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertEqual(estimate.race_label, "5K")
        self.assertEqual(estimate.performance_seconds, 19 * 60 + 59)
        self.assertEqual(estimate.observed_seconds, 20 * 60 + 2)
        self.assertEqual(estimate.source, "Strava best effort")
        self.assertAlmostEqual(estimate.vdot, 49.9, places=1)
        self.assertEqual(estimate.table_vdot, 50)

    @patch("running_agent.vdot.official_result_for_activity")
    def test_race_estimate_prefers_official_result_over_best_effort(
        self,
        official_result_for_activity,
    ) -> None:
        official_result_for_activity.return_value = {
            "distance": "5K",
            "distance_meters": 5000.0,
            "time_seconds": 19 * 60 + 59,
        }

        estimate = race_vdot_estimate(
            {
                "type": "Run",
                "name": "North Jersey Pride Run",
                "distance": 5068.1,
                "moving_time": 20 * 60 + 2,
                "workout_type": 1,
                "best_efforts": [
                    {
                        "name": "5K",
                        "distance": 5000,
                        "moving_time": 19 * 60 + 46,
                    }
                ],
            }
        )

        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertEqual(estimate.performance_seconds, 19 * 60 + 59)
        self.assertEqual(estimate.source, "official saved race result")
        self.assertAlmostEqual(estimate.vdot, 49.9, places=1)

    def test_race_vdot_context_includes_table_paces(self) -> None:
        context = race_vdot_context(
            [
                {
                    "type": "Run",
                    "name": "North Jersey Pride Run",
                    "distance": 5068.1,
                    "moving_time": 20 * 60 + 2,
                    "workout_type": 1,
                    "best_efforts": [
                        {
                            "name": "5K",
                            "distance": 5000,
                            "moving_time": 19 * 60 + 59,
                        }
                    ],
                }
            ]
        )

        self.assertIn("5K in 19:59 from Strava best effort", context)
        self.assertIn("full activity 3.15 mi in 20:02", context)
        self.assertIn("VDOT 49.9", context)
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

    def test_race_name_without_strava_race_tag_does_not_get_estimate(self) -> None:
        self.assertIsNone(
            race_vdot_estimate(
                {
                    "type": "Run",
                    "name": "Untagged 10K Race",
                    "distance": 10_000,
                    "moving_time": 42 * 60,
                }
            )
        )

    @patch("running_agent.vdot.official_result_for_activity")
    def test_official_result_without_strava_race_tag_gets_estimate(
        self,
        official_result_for_activity,
    ) -> None:
        official_result_for_activity.return_value = {
            "distance": "Marathon",
            "distance_meters": 42195.0,
            "time_seconds": 3 * 3600 + 19 * 60 + 24,
        }

        estimate = race_vdot_estimate(
            {
                "type": "Run",
                "name": "Wineglass Marathon",
                "distance": 42_195,
                "moving_time": 3 * 3600 + 20 * 60,
            }
        )

        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertEqual(estimate.race_label, "Marathon")
        self.assertEqual(estimate.source, "official saved race result")


if __name__ == "__main__":
    unittest.main()
