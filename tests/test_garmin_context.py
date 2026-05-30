from __future__ import annotations

import unittest

from running_agent.garmin_context import (
    format_garmin_readiness_context,
    format_garmin_weekly_context,
)


class GarminContextTest(unittest.TestCase):
    def test_format_garmin_readiness_context_summarizes_available_fields(self) -> None:
        context = format_garmin_readiness_context(
            {
                "date": "2026-05-30",
                "sleep": {
                    "available": True,
                    "data": {
                        "dailySleepDTO": {"sleepTimeSeconds": 25020},
                        "sleepScores": {"overall": {"value": 77}},
                    },
                },
                "hrv": {
                    "available": True,
                    "data": {"hrvSummary": {"lastNightAvg": 42, "status": "BALANCED"}},
                },
                "heart_rates": {"available": True, "data": {"restingHeartRate": 48}},
                "stats": {"available": True, "data": {}},
                "stress": {"available": True, "data": {"avgStressLevel": 31, "maxStressLevel": 74}},
                "body_battery": {
                    "available": True,
                    "data": [{"bodyBatteryValuesArray": [[1, 40], [3, 82]]}],
                },
                "training_readiness": {
                    "available": True,
                    "data": [
                        {"timestampLocal": "2026-05-30T07:00:00", "score": 74, "level": "MODERATE"},
                        {"timestampLocal": "2026-05-30T11:00:00", "score": 34, "level": "LOW"},
                    ],
                },
                "training_status": {
                    "available": True,
                    "data": {
                        "mostRecentTrainingStatus": {
                            "latestTrainingStatusData": {
                                "3617037508": {
                                    "calendarDate": "2026-05-30",
                                    "trainingStatusFeedbackPhrase": "PRODUCTIVE_3",
                                }
                            }
                        }
                    },
                },
                "vo2max": {
                    "available": True,
                    "data": [{"generic": {"vo2MaxPreciseValue": 55.3}}],
                },
            }
        )

        self.assertIn("Garmin readiness context for 2026-05-30:", context)
        self.assertIn("Sleep: 6h 57m, score 77.", context)
        self.assertIn("HRV: 42 ms, BALANCED.", context)
        self.assertIn("Resting HR: 48 bpm.", context)
        self.assertIn("Stress: avg 31, max 74.", context)
        self.assertIn("Body Battery: latest 82, high 82, low 40.", context)
        self.assertIn("Training readiness: 34, LOW.", context)
        self.assertIn("Training status: Productive 3.", context)
        self.assertIn("VO2 max: 55.3.", context)

    def test_format_garmin_readiness_context_reports_missing_fields(self) -> None:
        context = format_garmin_readiness_context(
            {
                "date": "2026-05-30",
                "sleep": {"available": False, "error": "sleep failed"},
            }
        )

        self.assertIn("Sleep: unavailable.", context)
        self.assertIn("Missing Garmin fields: sleep: sleep failed", context)

    def test_sleep_duration_falls_back_to_sleep_stages(self) -> None:
        context = format_garmin_readiness_context(
            {
                "date": "2026-05-30",
                "sleep": {
                    "available": True,
                    "data": {
                        "dailySleepDTO": {
                            "sleepTimeSeconds": None,
                            "deepSleepSeconds": 3600,
                            "lightSleepSeconds": 14400,
                            "remSleepSeconds": 3600,
                        }
                    },
                },
            }
        )

        self.assertIn("Sleep: 6h 00m.", context)

    def test_format_garmin_weekly_context_summarizes_recovery_trends(self) -> None:
        context = format_garmin_weekly_context(
            [
                _snapshot(
                    "2026-05-24",
                    readiness=32,
                    level="LOW",
                    rhr=47,
                    stress=44,
                    battery_low=28,
                    sleep_hours=5.5,
                    vo2=51.8,
                ),
                _snapshot(
                    "2026-05-25",
                    readiness=62,
                    level="MODERATE",
                    rhr=44,
                    stress=31,
                    battery_low=42,
                    sleep_hours=7.0,
                    vo2=51.9,
                ),
                _snapshot(
                    "2026-05-26",
                    readiness=38,
                    level="LOW",
                    rhr=46,
                    stress=41,
                    battery_low=35,
                    sleep_hours=5.8,
                    vo2=52.0,
                ),
            ]
        )

        self.assertIn("Garmin recovery context, last 3 days:", context)
        self.assertIn("Training readiness: avg 44, low days 2, latest 38 (Low).", context)
        self.assertIn("Resting HR: avg 46 bpm, latest 46 bpm.", context)
        self.assertIn("Stress: avg 39, high-stress days 2.", context)
        self.assertIn("Body Battery: avg daily low 35, days below 40 2.", context)
        self.assertIn("Sleep: avg 6.1h, short nights 2.", context)
        self.assertIn("VO2 max: latest 52.0.", context)


def _snapshot(
    date: str,
    readiness: int,
    level: str,
    rhr: int,
    stress: int,
    battery_low: int,
    sleep_hours: float,
    vo2: float,
) -> dict:
    return {
        "date": date,
        "training_readiness": {
            "available": True,
            "data": [{"timestampLocal": f"{date}T07:00:00", "score": readiness, "level": level}],
        },
        "heart_rates": {"available": True, "data": {"restingHeartRate": rhr}},
        "stats": {
            "available": True,
            "data": {
                "bodyBatteryLowestValue": battery_low,
                "bodyBatteryMostRecentValue": battery_low + 10,
                "bodyBatteryHighestValue": battery_low + 40,
            },
        },
        "stress": {"available": True, "data": {"avgStressLevel": stress}},
        "sleep": {
            "available": True,
            "data": {"dailySleepDTO": {"sleepTimeSeconds": sleep_hours * 3600}},
        },
        "vo2max": {"available": True, "data": [{"generic": {"vo2MaxPreciseValue": vo2}}]},
    }


if __name__ == "__main__":
    unittest.main()
