from __future__ import annotations

import unittest
from datetime import date, time
from unittest.mock import patch

from running_agent.weather_client import (
    OPEN_METEO_FORECAST_URL,
    enrich_activity_weather,
    weather_for_location_time,
    weather_summary,
)


class WeatherClientTest(unittest.TestCase):
    @patch(
        "running_agent.weather_client._fetch_open_meteo_hourly",
        return_value={
            "hourly": {
                "time": ["2026-06-23T05:00", "2026-06-23T06:00"],
                "temperature_2m": [72.0, 74.0],
                "apparent_temperature": [75.0, 78.0],
                "relative_humidity_2m": [88, 91],
                "dew_point_2m": [68.0, 71.0],
                "precipitation": [0.0, 0.01],
                "weather_code": [2, 61],
                "wind_speed_10m": [5.0, 7.0],
                "wind_gusts_10m": [9.0, 15.0],
            }
        },
    )
    def test_enrich_activity_weather_uses_start_location_and_time(self, fetch) -> None:
        activity = enrich_activity_weather(
            {
                "id": 1,
                "start_latlng": [40.743385, -74.25256],
                "start_date_local": "2026-06-23T05:45:35Z",
                "timezone": "(GMT-05:00) America/New_York",
            }
        )

        self.assertEqual(activity["weather"]["time"], "2026-06-23T06:00")
        self.assertEqual(activity["weather"]["temperature_f"], 74.0)
        self.assertEqual(activity["weather"]["relative_humidity"], 91)
        self.assertEqual(activity["weather"]["weather"], "light rain")
        fetch.assert_called_once_with(
            latitude=40.743385,
            longitude=-74.25256,
            start_date="2026-06-23",
            end_date="2026-06-23",
            timezone_name="America/New_York",
        )

    def test_enrich_activity_weather_skips_missing_location(self) -> None:
        activity = {"id": 1, "start_date_local": "2026-06-23T05:45:35Z"}

        self.assertIs(enrich_activity_weather(activity), activity)

    def test_weather_summary_formats_coaching_context(self) -> None:
        summary = weather_summary(
            {
                "temperature_f": 74.0,
                "apparent_temperature_f": 78.0,
                "relative_humidity": 91,
                "dew_point_f": 71.0,
                "wind_speed_mph": 7.0,
                "wind_gust_mph": 15.0,
                "precipitation_in": 0.01,
                "weather": "light rain",
            }
        )

        self.assertEqual(
            summary,
            "74F, feels 78F, 91% humidity, 71F dew point, "
            "wind 7 mph, gusts 15 mph, 0.01 in precip, light rain",
        )

    @patch(
        "running_agent.weather_client._fetch_open_meteo_hourly",
        return_value={
            "hourly": {
                "time": ["2026-06-23T05:00", "2026-06-23T06:00"],
                "temperature_2m": [70.0, 72.0],
            }
        },
    )
    def test_weather_for_location_time_uses_forecast_api(self, fetch) -> None:
        weather = weather_for_location_time(
            latitude=40.743385,
            longitude=-74.25256,
            target_date=date(2026, 6, 23),
            target_time=time(5, 30),
            timezone_name="America/New_York",
        )

        self.assertEqual(weather["temperature_f"], 70.0)
        fetch.assert_called_once_with(
            url=OPEN_METEO_FORECAST_URL,
            latitude=40.743385,
            longitude=-74.25256,
            start_date="2026-06-23",
            end_date="2026-06-23",
            timezone_name="America/New_York",
        )


if __name__ == "__main__":
    unittest.main()
