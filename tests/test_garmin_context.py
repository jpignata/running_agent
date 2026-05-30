from __future__ import annotations

import unittest

from running_agent.garmin_context import format_garmin_readiness_context


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


if __name__ == "__main__":
    unittest.main()
