from __future__ import annotations

import unittest

from running_agent.activity_format import activity_headline, detailed_activity_context


METERS_PER_MILE = 1609.344


class ActivityFormatTest(unittest.TestCase):
    def test_activity_headline_formats_core_run_facts(self) -> None:
        headline = activity_headline(
            {
                "name": "Morning Run",
                "distance": 6 * METERS_PER_MILE,
                "moving_time": 48 * 60,
                "start_date_local": "2026-05-29T05:45:00Z",
                "average_heartrate": 140.2,
            }
        )

        self.assertEqual(
            headline,
            "Morning Run: 6.00 mi on Friday, May 29, 8:00/mi, avg HR 140",
        )

    def test_activity_headline_handles_missing_time_and_date(self) -> None:
        headline = activity_headline({"distance": 0})

        self.assertEqual(headline, "Run: 0.00 mi on unknown date, unknown pace")

    def test_detailed_activity_context_includes_run_details_and_lap_signals(self) -> None:
        context = detailed_activity_context(
            {
                "name": "Track",
                "distance": 3 * METERS_PER_MILE,
                "moving_time": 24 * 60,
                "elapsed_time": 30 * 60,
                "start_date_local": "2026-05-27T05:45:00Z",
                "average_heartrate": 150,
                "max_heartrate": 174,
                "average_cadence": 86.2,
                "total_elevation_gain": 10,
                "elev_low": 70,
                "elev_high": 80,
                "device_name": "Garmin",
                "laps": [
                    _lap(1, 0.75, 4 * 60 + 55, 4 * 60 + 55, 161, 169),
                    _lap(2, 0.08, 3 * 60, 3 * 60, 124, 168),
                    _lap(3, 0.75, 4 * 60 + 56, 4 * 60 + 56, 163, 172),
                    _lap(4, 0.08, 3 * 60, 3 * 60, 132, 171),
                ],
            },
            target_date=None,
        )

        self.assertIn("Run details:", context)
        self.assertIn("- Distance: 3.00 mi", context)
        self.assertIn("- Elevation gain: 33 ft", context)
        self.assertIn("Derived workout signals:", context)
        self.assertIn("Quality-looking laps:", context)
        self.assertIn("Recovery-looking laps:", context)
        self.assertIn("Lap | Distance | Moving | Elapsed | Pace | Avg HR | Max HR | Elev gain", context)

    def test_detailed_activity_context_limits_laps(self) -> None:
        context = detailed_activity_context(
            {
                "name": "Lots of Laps",
                "distance": 3 * METERS_PER_MILE,
                "moving_time": 24 * 60,
                "start_date_local": "2026-05-27T05:45:00Z",
                "laps": [_lap(i, 0.25, 90, 90, 150, 160) for i in range(1, 4)],
            },
            max_laps=2,
        )

        self.assertIn("...1 additional laps omitted.", context)


def _lap(
    lap_index: int,
    distance_miles: float,
    moving_time: int,
    elapsed_time: int,
    average_heartrate: int,
    max_heartrate: int,
) -> dict:
    return {
        "lap_index": lap_index,
        "distance": distance_miles * METERS_PER_MILE,
        "moving_time": moving_time,
        "elapsed_time": elapsed_time,
        "average_heartrate": average_heartrate,
        "max_heartrate": max_heartrate,
        "total_elevation_gain": 0,
    }


if __name__ == "__main__":
    unittest.main()
