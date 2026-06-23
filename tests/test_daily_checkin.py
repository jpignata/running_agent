from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from running_agent.daily_checkin import (
    DAILY_CHECKIN_STATE_KEY,
    current_weather_context,
    daily_workout_checkin,
    has_completed_run_for_date,
    has_planned_workout_for_date,
    mark_daily_checkin_sent,
    should_send_daily_checkin,
)

METERS_PER_MILE = 1609.344


class DailyCheckinTest(unittest.TestCase):
    def test_daily_checkin_trigger_only_after_530_once_per_day(self) -> None:
        state: dict[str, str] = {}
        before = datetime(2026, 5, 30, 9, 29, tzinfo=timezone.utc)
        at_time = datetime(2026, 5, 30, 9, 30, tzinfo=timezone.utc)

        self.assertFalse(should_send_daily_checkin(before, state))
        self.assertTrue(should_send_daily_checkin(at_time, state))

        mark_daily_checkin_sent(at_time, state)

        self.assertEqual(state[DAILY_CHECKIN_STATE_KEY], "2026-05-30")
        self.assertFalse(should_send_daily_checkin(at_time, state))

    def test_daily_checkin_trigger_uses_est_in_winter(self) -> None:
        state: dict[str, str] = {}
        before = datetime(2026, 1, 3, 10, 29, tzinfo=timezone.utc)
        at_time = datetime(2026, 1, 3, 10, 30, tzinfo=timezone.utc)

        self.assertFalse(should_send_daily_checkin(before, state))
        self.assertTrue(should_send_daily_checkin(at_time, state))

    def test_has_completed_run_for_date_checks_strava_date(self) -> None:
        client = _FakeStravaClient([])
        client.runs_by_date["2026-05-30"] = [{"id": 1}]

        self.assertTrue(has_completed_run_for_date(client, datetime(2026, 5, 30).date()))
        self.assertFalse(has_completed_run_for_date(client, datetime(2026, 5, 31).date()))
        self.assertEqual(client.search_days, 14)

    @patch("running_agent.daily_checkin.planned_workout_for_date", return_value="6 mi easy")
    def test_has_planned_workout_for_date_uses_weekly_plan(self, _planned) -> None:
        self.assertTrue(has_planned_workout_for_date(datetime(2026, 5, 30).date()))

    @patch("running_agent.daily_checkin.planned_workout_for_date", return_value=None)
    def test_has_planned_workout_for_date_handles_missing_plan_day(self, _planned) -> None:
        self.assertFalse(has_planned_workout_for_date(datetime(2026, 5, 30).date()))

    @patch("running_agent.daily_checkin.coach_log_context", return_value="Coach log context")
    @patch("running_agent.daily_checkin.training_goal_context", return_value="Goal context")
    @patch("running_agent.daily_checkin.current_weather_context", return_value="Weather context")
    @patch(
        "running_agent.daily_checkin.weekly_plan_context_for_date",
        return_value="Matched plan for today",
    )
    @patch("running_agent.daily_checkin.coaching_reply", return_value="Do the planned easy run.")
    def test_daily_workout_checkin_passes_garmin_plan_and_week_context_to_model(
        self,
        coaching_reply,
        _weekly_plan_context_for_date,
        _current_weather_context,
        _training_goal_context,
        _coach_log_context,
    ) -> None:
        client = _FakeStravaClient(
            [
                {
                    "type": "Run",
                    "name": "Easy Run",
                    "distance": 5 * METERS_PER_MILE,
                    "moving_time": 40 * 60,
                    "start_date_local": "2026-05-29T06:00:00Z",
                }
            ]
        )

        checkin = daily_workout_checkin(
            client,
            target_date=datetime(2026, 5, 30).date(),
            garmin_context_provider=lambda: "Garmin readiness context",
        )

        self.assertEqual(checkin, "Do the planned easy run.")
        self.assertEqual(client.requested_days, 7)
        kwargs = coaching_reply.call_args.kwargs
        self.assertIn("Reviewed 1 runs over the last 7 days.", kwargs["training_summary"])
        self.assertIn("Easy Run: 5.00 mi", kwargs["recent_runs"])
        self.assertEqual(kwargs["weekly_plan"], "Matched plan for today")
        self.assertEqual(kwargs["training_goal"], "Goal context")
        self.assertEqual(kwargs["coach_log"], "Coach log context")
        self.assertEqual(kwargs["garmin_context"], "Garmin readiness context")
        self.assertEqual(kwargs["weather_context"], "Weather context")
        self.assertFalse(kwargs["tools_enabled"])

    @patch(
        "running_agent.daily_checkin.weather_for_location_time",
        return_value={
            "temperature_f": 70,
            "apparent_temperature_f": 77,
            "relative_humidity": 99,
            "dew_point_f": 70,
            "wind_speed_mph": 2,
            "wind_gust_mph": 11,
            "weather": "drizzle",
        },
    )
    def test_current_weather_context_uses_latest_run_location(self, weather_for_location_time):
        context = current_weather_context(
            datetime(2026, 6, 23).date(),
            [
                {
                    "type": "Run",
                    "start_latlng": [40.743385, -74.25256],
                    "timezone": "(GMT-05:00) America/New_York",
                }
            ],
        )

        self.assertIn("Weather near latest known Strava start location", context)
        self.assertIn("70F, feels 77F, 99% humidity", context)
        weather_for_location_time.assert_called_once()
        self.assertEqual(weather_for_location_time.call_args.kwargs["latitude"], 40.743385)
        self.assertEqual(weather_for_location_time.call_args.kwargs["longitude"], -74.25256)
        self.assertEqual(
            weather_for_location_time.call_args.kwargs["timezone_name"], "America/New_York"
        )

    @patch(
        "running_agent.daily_checkin.weekly_plan_context_for_date",
        return_value="Matched plan for today",
    )
    @patch("running_agent.daily_checkin.coaching_reply", side_effect=RuntimeError("offline"))
    def test_daily_workout_checkin_raises_when_model_is_unavailable(
        self,
        _coaching_reply,
        _weekly_plan,
    ) -> None:
        with self.assertRaisesRegex(RuntimeError, "offline"):
            daily_workout_checkin(
                _FakeStravaClient([]),
                target_date=datetime(2026, 5, 30).date(),
                garmin_context_provider=lambda: "Garmin readiness context",
            )


class _FakeStravaClient:
    def __init__(self, activities: list[dict]):
        self.activities = activities
        self.requested_days: int | None = None
        self.runs_by_date: dict[str, list[dict]] = {}
        self.search_days: int | None = None

    def recent_activities(self, days: int) -> list[dict]:
        self.requested_days = days
        return self.activities

    def runs_on_date(self, target_date, search_days: int) -> list[dict]:
        self.search_days = search_days
        return self.runs_by_date.get(target_date.isoformat(), [])


if __name__ == "__main__":
    unittest.main()
