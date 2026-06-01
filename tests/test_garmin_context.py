from __future__ import annotations

import unittest
from datetime import date

from running_agent.garmin_client import GarminClient
from running_agent.garmin_context import (
    format_garmin_baseline_context,
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

    def test_format_garmin_readiness_context_labels_fallback_vo2max_date(self) -> None:
        context = format_garmin_readiness_context(
            {
                "date": "2026-05-30",
                "vo2max": {
                    "available": True,
                    "date": "2026-05-24",
                    "fallback_for_date": "2026-05-30",
                    "data": [{"generic": {"vo2MaxPreciseValue": 55.3}}],
                },
            }
        )

        self.assertIn("VO2 max: latest from 2026-05-24: 55.3.", context)

    def test_garmin_client_falls_back_to_recent_vo2max_measurement(self) -> None:
        client = GarminClient.__new__(GarminClient)
        client.api = _FakeGarminApi(
            vo2max_by_date={
                "2026-05-30": [],
                "2026-05-29": [],
                "2026-05-28": [{"generic": {"vo2MaxPreciseValue": 55.3}}],
            }
        )

        snapshot = client.readiness_snapshot(
            target_date=date(2026, 5, 30),
            vo2max_lookback_days=3,
        )

        self.assertEqual(snapshot["vo2max"]["date"], "2026-05-28")
        self.assertEqual(snapshot["vo2max"]["fallback_for_date"], "2026-05-30")
        self.assertEqual(snapshot["vo2max"]["data"][0]["generic"]["vo2MaxPreciseValue"], 55.3)

    def test_garmin_client_can_disable_vo2max_fallback(self) -> None:
        client = GarminClient.__new__(GarminClient)
        client.api = _FakeGarminApi(
            vo2max_by_date={
                "2026-05-30": [],
                "2026-05-29": [{"generic": {"vo2MaxPreciseValue": 55.3}}],
            }
        )

        snapshot = client.readiness_snapshot(
            target_date=date(2026, 5, 30),
            vo2max_lookback_days=0,
        )

        self.assertEqual(snapshot["vo2max"]["data"], [])
        self.assertNotIn("fallback_for_date", snapshot["vo2max"])

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
        snapshots = [
            _snapshot(
                "2026-05-24",
                readiness=32,
                level="LOW",
                hrv=41,
                hrv_status="LOW",
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
                hrv=46,
                hrv_status="BALANCED",
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
                hrv=43,
                hrv_status="LOW",
                rhr=46,
                stress=41,
                battery_low=35,
                sleep_hours=5.8,
                vo2=52.0,
            ),
        ]
        context = format_garmin_weekly_context(snapshots)

        self.assertIn("Garmin recovery context, last 3 days:", context)
        self.assertIn("Training readiness: avg 44, low days 2, latest 38 (Low).", context)
        self.assertIn("HRV: avg 43 ms, latest 43 ms (Low).", context)
        self.assertIn("Resting HR: avg 46 bpm, latest 46 bpm.", context)
        self.assertIn("Stress: avg 39, high-stress days 2.", context)
        self.assertIn("Body Battery: avg daily low 35, latest daily low 35.", context)
        self.assertIn("Sleep: avg 6.1h, latest 5.8h, range 5.5-7.0h.", context)
        self.assertNotIn("red flag", context)
        self.assertIn("VO2 max: latest 52.0.", context)

    def test_format_garmin_weekly_context_includes_baseline_when_provided(self) -> None:
        snapshots = [
            _snapshot(
                "2026-05-24",
                readiness=32,
                level="LOW",
                hrv=41,
                hrv_status="LOW",
                rhr=47,
                stress=44,
                battery_low=28,
                sleep_hours=5.5,
                vo2=51.8,
            )
        ]
        context = format_garmin_weekly_context(
            snapshots,
            baseline_snapshots=[
                _snapshot(
                    "2026-05-24",
                    readiness=32,
                    level="LOW",
                    hrv=41,
                    hrv_status="LOW",
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
                    hrv=46,
                    hrv_status="BALANCED",
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
                    hrv=43,
                    hrv_status="LOW",
                    rhr=46,
                    stress=41,
                    battery_low=35,
                    sleep_hours=5.8,
                    vo2=52.0,
                ),
            ],
        )

        self.assertIn("Athlete Garmin baseline, last 3 snapshots:", context)
        self.assertIn("Sleep: typical 5.5-7.0h, median 5.8h.", context)
        self.assertIn("Resting HR: typical 44-47 bpm, median 46 bpm.", context)
        self.assertIn("HRV: typical 41-46 ms, median 43 ms.", context)
        self.assertIn("Stress: typical 31-44, median 41.", context)
        self.assertIn("Body Battery low: typical 28-42, median 35.", context)
        self.assertIn("Training readiness: typical 32-62, median 38.", context)

    def test_format_garmin_baseline_context_uses_middle_range_for_larger_samples(self) -> None:
        context = format_garmin_baseline_context(
            [
                _snapshot(
                    f"2026-05-{20 + index}",
                    readiness=30 + index,
                    level="LOW",
                    hrv=40 + index,
                    hrv_status="BALANCED",
                    rhr=45 + index,
                    stress=20 + index,
                    battery_low=25 + index,
                    sleep_hours=5.0 + index * 0.25,
                    vo2=52.0,
                )
                for index in range(10)
            ]
        )

        self.assertIn("Athlete Garmin baseline, last 10 snapshots:", context)
        self.assertIn("Sleep: typical 5.2-7.0h, median 6.1h.", context)
        self.assertIn("Resting HR: typical 46-53 bpm, median 50 bpm.", context)


def _snapshot(
    date: str,
    readiness: int,
    level: str,
    hrv: int,
    hrv_status: str,
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
        "hrv": {
            "available": True,
            "data": {"hrvSummary": {"lastNightAvg": hrv, "status": hrv_status}},
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


class _FakeGarminApi:
    def __init__(self, vo2max_by_date: dict[str, list]):
        self.vo2max_by_date = vo2max_by_date

    def get_stats(self, date_text: str) -> dict:
        return {}

    def get_heart_rates(self, date_text: str) -> dict:
        return {}

    def get_sleep_data(self, date_text: str) -> dict:
        return {}

    def get_hrv_data(self, date_text: str) -> dict:
        return {}

    def get_stress_data(self, date_text: str) -> dict:
        return {}

    def get_body_battery(self, start_date_text: str, end_date_text: str) -> list:
        return []

    def get_max_metrics(self, date_text: str) -> list:
        return self.vo2max_by_date.get(date_text, [])


if __name__ == "__main__":
    unittest.main()
