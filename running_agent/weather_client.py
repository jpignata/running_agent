from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HOURLY = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_gusts_10m",
)


def enrich_activity_weather(activity: dict[str, Any]) -> dict[str, Any]:
    if isinstance(activity.get("weather"), dict):
        return activity
    weather = weather_for_activity(activity)
    if not weather:
        return activity
    return {**activity, "weather": weather}


def safe_enrich_activity_weather(activity: dict[str, Any]) -> dict[str, Any]:
    try:
        return enrich_activity_weather(activity)
    except Exception:
        return activity


def weather_for_activity(activity: dict[str, Any]) -> dict[str, Any] | None:
    latlng = activity.get("start_latlng")
    if not _valid_latlng(latlng):
        return None
    start = _activity_start(activity)
    if start is None:
        return None
    timezone_name = _activity_timezone(activity) or "auto"
    payload = _fetch_open_meteo_hourly(
        latitude=float(latlng[0]),
        longitude=float(latlng[1]),
        start_date=start.date().isoformat(),
        end_date=start.date().isoformat(),
        timezone_name=timezone_name,
    )
    return _weather_at_start(payload, start)


def weather_for_location_time(
    *,
    latitude: float,
    longitude: float,
    target_date: date,
    target_time: time,
    timezone_name: str = "auto",
) -> dict[str, Any] | None:
    payload = _fetch_open_meteo_hourly(
        url=OPEN_METEO_FORECAST_URL,
        latitude=latitude,
        longitude=longitude,
        start_date=target_date.isoformat(),
        end_date=target_date.isoformat(),
        timezone_name=timezone_name,
    )
    return _weather_at_start(payload, datetime.combine(target_date, target_time))


def weather_summary(weather: dict[str, Any] | None) -> str | None:
    if not isinstance(weather, dict):
        return None
    parts = []
    temp = _number(weather.get("temperature_f"))
    feels = _number(weather.get("apparent_temperature_f"))
    humidity = _number(weather.get("relative_humidity"))
    dew_point = _number(weather.get("dew_point_f"))
    wind = _number(weather.get("wind_speed_mph"))
    gust = _number(weather.get("wind_gust_mph"))
    precipitation = _number(weather.get("precipitation_in"))
    code_label = weather.get("weather")

    if temp is not None and feels is not None:
        parts.append(f"{temp:.0f}F, feels {feels:.0f}F")
    elif temp is not None:
        parts.append(f"{temp:.0f}F")
    if humidity is not None:
        parts.append(f"{humidity:.0f}% humidity")
    if dew_point is not None:
        parts.append(f"{dew_point:.0f}F dew point")
    if wind is not None and gust is not None and gust >= wind + 5:
        parts.append(f"wind {wind:.0f} mph, gusts {gust:.0f} mph")
    elif wind is not None:
        parts.append(f"wind {wind:.0f} mph")
    if precipitation is not None and precipitation > 0:
        parts.append(f"{precipitation:.2f} in precip")
    if isinstance(code_label, str) and code_label:
        parts.append(code_label)
    if not parts:
        return None
    return ", ".join(parts)


def _fetch_open_meteo_hourly(
    *,
    url: str = OPEN_METEO_ARCHIVE_URL,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    timezone_name: str,
) -> dict[str, Any]:
    params = {
        "latitude": f"{latitude:.6f}",
        "longitude": f"{longitude:.6f}",
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(OPEN_METEO_HOURLY),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": timezone_name,
    }
    request = Request(f"{url}?{urlencode(params)}")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _weather_at_start(payload: dict[str, Any], start: datetime) -> dict[str, Any] | None:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return None
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        return None
    index = _nearest_time_index(times, start)
    if index is None:
        return None
    code = _hourly_value(hourly, "weather_code", index)
    return {
        "source": "open-meteo",
        "time": times[index],
        "temperature_f": _hourly_value(hourly, "temperature_2m", index),
        "apparent_temperature_f": _hourly_value(hourly, "apparent_temperature", index),
        "relative_humidity": _hourly_value(hourly, "relative_humidity_2m", index),
        "dew_point_f": _hourly_value(hourly, "dew_point_2m", index),
        "precipitation_in": _hourly_value(hourly, "precipitation", index),
        "weather_code": code,
        "weather": _weather_code_label(code),
        "wind_speed_mph": _hourly_value(hourly, "wind_speed_10m", index),
        "wind_gust_mph": _hourly_value(hourly, "wind_gusts_10m", index),
    }


def _nearest_time_index(times: list[Any], start: datetime) -> int | None:
    best_index = None
    best_delta = None
    for index, value in enumerate(times):
        if not isinstance(value, str):
            continue
        try:
            current = datetime.fromisoformat(value)
        except ValueError:
            continue
        delta = abs((current - start.replace(tzinfo=None)).total_seconds())
        if best_delta is None or delta < best_delta:
            best_index = index
            best_delta = delta
    return best_index


def _hourly_value(hourly: dict[str, Any], key: str, index: int) -> Any:
    values = hourly.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _valid_latlng(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    )


def _activity_start(activity: dict[str, Any]) -> datetime | None:
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _activity_timezone(activity: dict[str, Any]) -> str | None:
    timezone_value = activity.get("timezone")
    if not isinstance(timezone_value, str):
        return None
    if ")" in timezone_value:
        return timezone_value.split(")", 1)[1].strip() or None
    return timezone_value.strip() or None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _weather_code_label(code: Any) -> str | None:
    if not isinstance(code, (int, float)):
        return None
    labels = {
        0: "clear",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "rime fog",
        51: "light drizzle",
        53: "drizzle",
        55: "heavy drizzle",
        61: "light rain",
        63: "rain",
        65: "heavy rain",
        71: "light snow",
        73: "snow",
        75: "heavy snow",
        80: "light showers",
        81: "showers",
        82: "heavy showers",
        95: "thunderstorm",
    }
    return labels.get(int(code))
