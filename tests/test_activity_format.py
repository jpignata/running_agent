from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from running_agent.activity_format import (
    activity_headline,
    detailed_activity_context,
    recent_runs_context,
)

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

    def test_detailed_activity_context_includes_run_details_and_lap_signals(
        self,
    ) -> None:
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
                "weather": {
                    "temperature_f": 74,
                    "apparent_temperature_f": 78,
                    "relative_humidity": 91,
                    "dew_point_f": 71,
                    "wind_speed_mph": 7,
                    "wind_gust_mph": 15,
                    "weather": "partly cloudy",
                },
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
        self.assertIn(
            "- Weather near start: 74F, feels 78F, 91% humidity, 71F dew point, "
            "wind 7 mph, gusts 15 mph, partly cloudy",
            context,
        )
        self.assertIn("Derived workout signals:", context)
        self.assertIn("Quality-looking reps:", context)
        self.assertIn("2 x 1200m / 0.75 mi", context)
        self.assertIn("Recovery-looking segments:", context)
        self.assertIn("2 x 3:00 recoveries", context)
        self.assertIn(
            "Lap | Distance | Moving | Elapsed | Pace | Avg HR | Max HR | Elev gain",
            context,
        )

    def test_detailed_activity_context_includes_percent_max_hr_when_reference_is_known(
        self,
    ) -> None:
        context = detailed_activity_context(
            {
                "name": "Easy",
                "distance": 5 * METERS_PER_MILE,
                "moving_time": 40 * 60,
                "start_date_local": "2026-05-27T05:45:00Z",
                "average_heartrate": 141,
                "max_heartrate": 160,
                "laps": [_lap(1, 5, 40 * 60, 40 * 60, 141, 160)],
            },
            max_heart_rate=180,
        )

        self.assertIn("avg HR 141 bpm (78% max HR)", context)
        self.assertIn("- Average HR: 141 bpm (78% max HR)", context)
        self.assertIn("- Max HR: 160 bpm (89% max HR)", context)
        self.assertIn("141 bpm (78% max HR) | 160 bpm (89% max HR)", context)

    def test_detailed_activity_context_buckets_noisy_800m_reps_together(self) -> None:
        context = detailed_activity_context(
            {
                "name": "Track",
                "distance": 2 * METERS_PER_MILE,
                "moving_time": 13 * 60,
                "start_date_local": "2026-06-03T05:45:00Z",
                "laps": [
                    _lap_meters(8, 790.34, 185, 185),
                    _lap_meters(10, 804.67, 200, 200),
                    _lap_meters(11, 804.67, 203, 203),
                    _lap_meters(13, 804.67, 205, 205),
                    _lap_meters(15, 804.67, 200, 200),
                    _lap_meters(17, 804.67, 209, 209),
                ],
            }
        )

        self.assertIn("6 x 800m / 0.50 mi (laps 8, 10, 11, 13, 15, 17)", context)
        self.assertNotIn("1 x 0.49 mi", context)

    def test_detailed_activity_context_identifies_short_fast_reps(self) -> None:
        context = detailed_activity_context(
            {
                "name": "Track",
                "distance": 2 * METERS_PER_MILE,
                "moving_time": 13 * 60,
                "start_date_local": "2026-06-03T05:45:00Z",
                "laps": [
                    _lap_meters(18, 58.77, 60, 59),
                    _lap_meters(19, 101.43, 20, 20),
                    _lap_meters(20, 146.63, 40, 40),
                    _lap_meters(21, 102.83, 20, 20),
                    _lap_meters(22, 103.55, 40, 40),
                    _lap_meters(23, 88.72, 20, 20),
                    _lap_meters(24, 107.74, 40, 40),
                    _lap_meters(25, 92.85, 20, 20),
                    _lap_meters(26, 113.01, 40, 40),
                ],
            }
        )

        self.assertIn("Short fast reps:", context)
        self.assertIn("4 x 20s (laps 19, 21, 23, 25)", context)
        self.assertIn("5:17/mi, 5:13/mi, 6:02/mi, 5:46/mi", context)
        self.assertIn("avg 5:33/mi", context)

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

    @patch("running_agent.activity_format.coach_today", return_value=date(2026, 6, 4))
    def test_recent_runs_context_states_when_no_run_is_recorded_today(
        self,
        _coach_today,
    ) -> None:
        context = recent_runs_context(
            [
                {
                    "type": "Run",
                    "name": "Track",
                    "distance": 7 * METERS_PER_MILE,
                    "moving_time": 56 * 60,
                    "start_date_local": "2026-06-03T05:45:00Z",
                    "average_heartrate": 144,
                    "max_heartrate": 180,
                }
            ]
        )

        self.assertIn(
            "Current Strava status for Thursday, Jun 4: no synced run recorded today.",
            context,
        )
        self.assertIn(
            "Latest synced run is Track: 7.00 mi on Wednesday, Jun 3, 8:00/mi, "
            "avg HR 144 bpm (80% max HR)",
            context,
        )
        self.assertIn("Heart-rate percentages use observed max HR 180 bpm.", context)

    @patch("running_agent.activity_format.coach_today", return_value=date(2026, 6, 4))
    def test_recent_runs_context_states_when_run_is_recorded_today(
        self,
        _coach_today,
    ) -> None:
        context = recent_runs_context(
            [
                {
                    "type": "Run",
                    "name": "Easy 5",
                    "distance": 5 * METERS_PER_MILE,
                    "moving_time": 40 * 60,
                    "start_date_local": "2026-06-04T05:45:00Z",
                }
            ]
        )

        self.assertIn(
            "Current Strava status for Thursday, Jun 4: 1 synced run(s) recorded today.",
            context,
        )
        self.assertIn("- Easy 5: 5.00 mi on Thursday, Jun 4", context)

    @patch("running_agent.activity_format.coach_today", return_value=date(2026, 6, 12))
    def test_recent_runs_context_includes_current_week_breakdown(
        self,
        _coach_today,
    ) -> None:
        context = recent_runs_context(
            [
                _run("Friday", 7.05, "2026-06-12T07:00:00"),
                _run("Wednesday", 7.37, "2026-06-10T07:00:00"),
                _run("Tuesday", 5.07, "2026-06-09T07:00:00"),
                _run("Prior Sunday", 10.0, "2026-06-07T07:00:00"),
            ]
        )

        self.assertIn(
            "Current week mileage from synced Strava runs "
            "(Monday, Jun 8 through Sunday, Jun 14; today is Friday, Jun 12):",
            context,
        )
        self.assertIn("- Monday: no synced run recorded", context)
        self.assertIn("- Tuesday: 5.07 mi", context)
        self.assertIn("- Wednesday: 7.37 mi", context)
        self.assertIn("- Thursday: no synced run recorded", context)
        self.assertIn("- Friday: 7.05 mi", context)
        self.assertIn("- Saturday: future day, not included in current total", context)
        self.assertIn("Current week total through today: 19.49 mi.", context)


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


def _lap_meters(
    lap_index: int,
    distance_meters: float,
    moving_time: int,
    elapsed_time: int,
) -> dict:
    return {
        "lap_index": lap_index,
        "distance": distance_meters,
        "moving_time": moving_time,
        "elapsed_time": elapsed_time,
        "average_heartrate": 155,
        "max_heartrate": 165,
        "total_elevation_gain": 0,
    }


def _run(name: str, distance_miles: float, start_date_local: str) -> dict:
    return {
        "type": "Run",
        "name": name,
        "distance": distance_miles * METERS_PER_MILE,
        "moving_time": int(distance_miles * 8 * 60),
        "start_date_local": start_date_local,
    }


if __name__ == "__main__":
    unittest.main()
