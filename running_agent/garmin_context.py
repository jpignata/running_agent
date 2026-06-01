from __future__ import annotations

from datetime import date
from typing import Any

from .garmin_cache import cached_garmin_snapshots, refresh_garmin_snapshots
from .garmin_client import GarminClient

NUMERIC_TYPES = (int, float)
DAILY_BASELINE_DAYS = 14
WEEKLY_BASELINE_DAYS = 45


def garmin_readiness_context(
    client: GarminClient | None = None,
    target_date: date | None = None,
    baseline_days: int = DAILY_BASELINE_DAYS,
) -> str:
    client = client or GarminClient()
    target_date = target_date or date.today()
    snapshots = cached_garmin_snapshots(target_date, 1)
    baseline_snapshots = cached_garmin_snapshots(target_date, baseline_days)
    if not snapshots:
        refresh_garmin_snapshots(client, end_date=target_date, days=max(1, baseline_days))
        snapshots = cached_garmin_snapshots(target_date, 1)
        baseline_snapshots = cached_garmin_snapshots(target_date, baseline_days)
    snapshot = snapshots[-1] if snapshots else client.readiness_snapshot(target_date=target_date)
    return format_garmin_readiness_context(snapshot, baseline_snapshots=baseline_snapshots)


def garmin_weekly_context(
    client: GarminClient | None = None,
    days: int = 7,
    baseline_days: int = WEEKLY_BASELINE_DAYS,
) -> str:
    client = client or GarminClient()
    today = date.today()
    snapshots = cached_garmin_snapshots(today, days)
    baseline_snapshots = cached_garmin_snapshots(today, baseline_days)
    if len(snapshots) < days:
        refresh_garmin_snapshots(client, end_date=today, days=max(days, baseline_days))
        snapshots = cached_garmin_snapshots(today, days)
        baseline_snapshots = cached_garmin_snapshots(today, baseline_days)
    return format_garmin_weekly_context(snapshots, baseline_snapshots=baseline_snapshots)


def safe_garmin_weekly_context(days: int = 7) -> str:
    try:
        return garmin_weekly_context(days=days)
    except RuntimeError as error:
        return f"Garmin recovery context unavailable: {error}"


def format_garmin_weekly_context(
    snapshots: list[dict[str, Any]],
    baseline_snapshots: list[dict[str, Any]] | None = None,
) -> str:
    if not snapshots:
        return "Garmin recovery context: no recent Garmin snapshots available."

    readiness_scores: list[float] = []
    readiness_levels: list[str] = []
    hrv_values: list[float] = []
    hrv_statuses: list[str] = []
    resting_hrs: list[float] = []
    stress_avgs: list[float] = []
    body_battery_lows: list[float] = []
    sleep_hours: list[float] = []
    vo2_values: list[float] = []

    for snapshot in snapshots:
        readiness = _latest_dict(_as_list(_data(snapshot, "training_readiness")))
        score = _first_number(readiness, ["score", "trainingReadinessScore"])
        level = _first_string(readiness, ["level", "feedbackShort", "feedbackLong"])
        if score is not None:
            readiness_scores.append(score)
        if level:
            readiness_levels.append(_humanize_status(level))

        hrv = _data(snapshot, "hrv")
        if isinstance(hrv, dict):
            hrv_value = _nested_first(
                hrv,
                [
                    ["hrvSummary", "lastNightAvg"],
                    ["hrvSummary", "weeklyAvg"],
                    ["lastNightAvg"],
                    ["weeklyAvg"],
                ],
            )
            hrv_status = _nested_first(hrv, [["hrvSummary", "status"], ["status"]])
            if isinstance(hrv_value, NUMERIC_TYPES):
                hrv_values.append(float(hrv_value))
            if isinstance(hrv_status, str) and hrv_status.strip():
                hrv_statuses.append(_humanize_status(hrv_status))

        heart_rates = _data(snapshot, "heart_rates")
        stats = _data(snapshot, "stats")
        resting_hr = None
        if isinstance(heart_rates, dict):
            resting_hr = _first_number(heart_rates, ["restingHeartRate", "restingHR"])
        if resting_hr is None and isinstance(stats, dict):
            resting_hr = _first_number(stats, ["restingHeartRate", "restingHR"])
        if resting_hr is not None:
            resting_hrs.append(resting_hr)

        stress = _data(snapshot, "stress")
        if isinstance(stress, dict):
            stress_avg = _first_number(
                stress,
                ["avgStressLevel", "averageStressLevel", "overallStressLevel"],
            )
            if stress_avg is not None:
                stress_avgs.append(stress_avg)

        low_battery = _body_battery_low(_data(snapshot, "body_battery"), stats)
        if low_battery is not None:
            body_battery_lows.append(low_battery)

        sleep_seconds = _sleep_seconds(_data(snapshot, "sleep"))
        if sleep_seconds is not None:
            sleep_hours.append(sleep_seconds / 3600)

        vo2 = _vo2_value(_data(snapshot, "vo2max"))
        if vo2 is not None:
            vo2_values.append(vo2)

    lines = [f"Garmin recovery context, last {len(snapshots)} days:"]
    if readiness_scores:
        lines.append(
            "Training readiness: "
            f"avg {_mean(readiness_scores):.0f}, "
            f"low days {sum(score < 40 for score in readiness_scores)}, "
            f"latest {readiness_scores[-1]:.0f}"
            + (f" ({readiness_levels[-1]})" if readiness_levels else "")
            + "."
        )
    else:
        lines.append("Training readiness: unavailable.")

    if hrv_values:
        line = f"HRV: avg {_mean(hrv_values):.0f} ms, latest {hrv_values[-1]:.0f} ms"
        if hrv_statuses:
            line += f" ({hrv_statuses[-1]})"
        lines.append(line + ".")
    else:
        lines.append("HRV: unavailable.")

    if resting_hrs:
        lines.append(
            f"Resting HR: avg {_mean(resting_hrs):.0f} bpm, latest {resting_hrs[-1]:.0f} bpm."
        )
    if stress_avgs:
        lines.append(
            f"Stress: avg {_mean(stress_avgs):.0f}, high-stress days {sum(value >= 40 for value in stress_avgs)}."
        )
    if body_battery_lows:
        lines.append(
            "Body Battery: "
            f"avg daily low {_mean(body_battery_lows):.0f}, "
            f"latest daily low {body_battery_lows[-1]:.0f}."
        )
    if sleep_hours:
        lines.append(
            "Sleep: "
            f"avg {_mean(sleep_hours):.1f}h, "
            f"latest {sleep_hours[-1]:.1f}h, "
            f"range {min(sleep_hours):.1f}-{max(sleep_hours):.1f}h."
        )
    else:
        lines.append("Sleep: unavailable or no duration fields found.")
    if vo2_values:
        lines.append(f"VO2 max: latest {vo2_values[-1]:.1f}.")
    if baseline_snapshots:
        lines.append("")
        lines.append(format_garmin_baseline_context(baseline_snapshots))

    return "\n".join(lines)


def format_garmin_readiness_context(
    snapshot: dict[str, Any],
    baseline_snapshots: list[dict[str, Any]] | None = None,
) -> str:
    lines = [f"Garmin readiness context for {snapshot.get('date', 'unknown date')}:"]

    lines.extend(
        [
            _sleep_line(_data(snapshot, "sleep")),
            _hrv_line(_data(snapshot, "hrv")),
            _resting_hr_line(_data(snapshot, "heart_rates"), _data(snapshot, "stats")),
            _stress_line(_data(snapshot, "stress")),
            _body_battery_line(_data(snapshot, "body_battery"), _data(snapshot, "stats")),
            _training_readiness_line(_data(snapshot, "training_readiness")),
            _training_status_line(_data(snapshot, "training_status")),
            _vo2_line(_data(snapshot, "vo2max")),
        ]
    )

    errors = _error_lines(snapshot)
    if errors:
        lines.append("Missing Garmin fields: " + "; ".join(errors))
    if baseline_snapshots:
        lines.append("")
        lines.append(format_garmin_baseline_context(baseline_snapshots))

    return "\n".join(line for line in lines if line)


def format_garmin_baseline_context(snapshots: list[dict[str, Any]]) -> str:
    metrics = _baseline_metrics(snapshots)
    if not metrics:
        return "Athlete Garmin baseline: unavailable."

    lines = [f"Athlete Garmin baseline, last {len(snapshots)} snapshots:"]
    _append_baseline_line(lines, "Sleep", metrics.get("sleep_hours"), "h", decimals=1)
    _append_baseline_line(lines, "Resting HR", metrics.get("resting_hr"), " bpm")
    _append_baseline_line(lines, "HRV", metrics.get("hrv"), " ms")
    _append_baseline_line(lines, "Stress", metrics.get("stress"), "")
    _append_baseline_line(lines, "Body Battery low", metrics.get("body_battery_low"), "")
    _append_baseline_line(lines, "Training readiness", metrics.get("readiness"), "")
    return "\n".join(lines)


def _data(snapshot: dict[str, Any], key: str) -> Any:
    value = snapshot.get(key)
    if isinstance(value, dict) and value.get("available"):
        data = value.get("data")
        if key == "vo2max" and value.get("fallback_for_date"):
            if isinstance(data, dict):
                data = dict(data)
                data["_source_date"] = value.get("date")
            elif isinstance(data, list):
                data = {"values": data, "_source_date": value.get("date")}
        return data
    return None


def _baseline_metrics(snapshots: list[dict[str, Any]]) -> dict[str, list[float]]:
    metrics: dict[str, list[float]] = {
        "sleep_hours": [],
        "resting_hr": [],
        "hrv": [],
        "stress": [],
        "body_battery_low": [],
        "readiness": [],
    }
    for snapshot in snapshots:
        sleep_seconds = _sleep_seconds(_data(snapshot, "sleep"))
        if sleep_seconds is not None:
            metrics["sleep_hours"].append(sleep_seconds / 3600)

        heart_rates = _data(snapshot, "heart_rates")
        stats = _data(snapshot, "stats")
        resting_hr = None
        if isinstance(heart_rates, dict):
            resting_hr = _first_number(heart_rates, ["restingHeartRate", "restingHR"])
        if resting_hr is None and isinstance(stats, dict):
            resting_hr = _first_number(stats, ["restingHeartRate", "restingHR"])
        if resting_hr is not None:
            metrics["resting_hr"].append(resting_hr)

        hrv = _data(snapshot, "hrv")
        if isinstance(hrv, dict):
            hrv_value = _nested_first(
                hrv,
                [
                    ["hrvSummary", "lastNightAvg"],
                    ["hrvSummary", "weeklyAvg"],
                    ["lastNightAvg"],
                    ["weeklyAvg"],
                ],
            )
            if isinstance(hrv_value, NUMERIC_TYPES):
                metrics["hrv"].append(float(hrv_value))

        stress = _data(snapshot, "stress")
        if isinstance(stress, dict):
            stress_avg = _first_number(
                stress,
                ["avgStressLevel", "averageStressLevel", "overallStressLevel"],
            )
            if stress_avg is not None:
                metrics["stress"].append(stress_avg)

        low_battery = _body_battery_low(_data(snapshot, "body_battery"), stats)
        if low_battery is not None:
            metrics["body_battery_low"].append(low_battery)

        readiness = _latest_dict(_as_list(_data(snapshot, "training_readiness")))
        score = _first_number(readiness, ["score", "trainingReadinessScore"])
        if score is not None:
            metrics["readiness"].append(score)

    return {key: values for key, values in metrics.items() if values}


def _append_baseline_line(
    lines: list[str],
    label: str,
    values: list[float] | None,
    unit: str,
    decimals: int = 0,
) -> None:
    if not values:
        return
    low, high = _typical_range(values)
    median = _median(values)
    lines.append(
        f"{label}: typical {_format_number(low, decimals)}-{_format_number(high, decimals)}"
        f"{unit}, median {_format_number(median, decimals)}{unit}."
    )


def _error_lines(snapshot: dict[str, Any]) -> list[str]:
    errors = []
    for key, value in snapshot.items():
        if isinstance(value, dict) and not value.get("available") and value.get("error"):
            errors.append(f"{key}: {value['error']}")
    return errors


def _sleep_line(data: Any) -> str:
    if not isinstance(data, dict):
        return "Sleep: unavailable."
    seconds = _sleep_seconds(data)
    score = _nested_first(data, [["sleepScores", "overall", "value"], ["sleepScore", "value"]])
    parts = []
    if seconds:
        parts.append(_duration(seconds))
    if score:
        parts.append(f"score {score:.0f}")
    return "Sleep: " + (", ".join(parts) + "." if parts else "available, no summary fields found.")


def _hrv_line(data: Any) -> str:
    if not isinstance(data, dict):
        return "HRV: unavailable."
    hrv = _nested_first(
        data,
        [
            ["hrvSummary", "lastNightAvg"],
            ["hrvSummary", "weeklyAvg"],
            ["lastNightAvg"],
            ["weeklyAvg"],
        ],
    )
    status = _nested_first(data, [["hrvSummary", "status"], ["status"]])
    if hrv and status:
        return f"HRV: {hrv:.0f} ms, {status}."
    if hrv:
        return f"HRV: {hrv:.0f} ms."
    if status:
        return f"HRV: {status}."
    return "HRV: available, no summary fields found."


def _resting_hr_line(heart_rates: Any, stats: Any) -> str:
    value = None
    if isinstance(heart_rates, dict):
        value = _first_number(heart_rates, ["restingHeartRate", "restingHR"])
    if value is None and isinstance(stats, dict):
        value = _first_number(stats, ["restingHeartRate", "restingHR"])
    return f"Resting HR: {value:.0f} bpm." if value else "Resting HR: unavailable."


def _stress_line(data: Any) -> str:
    if not isinstance(data, dict):
        return "Stress: unavailable."
    avg = _first_number(data, ["avgStressLevel", "averageStressLevel", "overallStressLevel"])
    max_value = _first_number(data, ["maxStressLevel"])
    if avg and max_value:
        return f"Stress: avg {avg:.0f}, max {max_value:.0f}."
    if avg:
        return f"Stress: avg {avg:.0f}."
    return "Stress: available, no summary fields found."


def _body_battery_line(data: Any, stats: Any) -> str:
    if isinstance(stats, dict):
        latest = _first_number(stats, ["bodyBatteryMostRecentValue"])
        high = _first_number(stats, ["bodyBatteryHighestValue"])
        low = _first_number(stats, ["bodyBatteryLowestValue"])
        if latest is not None and high is not None and low is not None:
            return f"Body Battery: latest {latest:.0f}, high {high:.0f}, low {low:.0f}."

    if not isinstance(data, list):
        return "Body Battery: unavailable."
    values = []
    for day in data:
        if isinstance(day, dict):
            values.extend(day.get("bodyBatteryValuesArray") or [])
    scores = [
        row[1]
        for row in values
        if isinstance(row, list) and len(row) >= 2 and isinstance(row[1], NUMERIC_TYPES)
    ]
    if not scores:
        return "Body Battery: available, no summary fields found."
    return f"Body Battery: latest {scores[-1]:.0f}, high {max(scores):.0f}, low {min(scores):.0f}."


def _training_readiness_line(data: Any) -> str:
    if isinstance(data, list):
        data = _latest_dict(data)
    if not isinstance(data, dict):
        return "Training readiness: unavailable."
    score = _first_number(data, ["score", "trainingReadinessScore"])
    level = _first_string(data, ["level", "feedbackLong", "feedbackPhrase"])
    if score and level:
        return f"Training readiness: {score:.0f}, {level}."
    if score:
        return f"Training readiness: {score:.0f}."
    if level:
        return f"Training readiness: {level}."
    return "Training readiness: available, no summary fields found."


def _training_status_line(data: Any) -> str:
    if not isinstance(data, dict):
        return "Training status: unavailable."
    latest = _nested_first(data, [["mostRecentTrainingStatus", "latestTrainingStatusData"]])
    if isinstance(latest, dict):
        latest = _latest_dict(list(latest.values()))
        status = _first_string(latest, ["trainingStatusFeedbackPhrase", "acwrStatus"])
        if status:
            return f"Training status: {_humanize_status(status)}."

    status = _nested_first(
        data,
        [
            ["mostRecentTrainingStatus", "trainingStatus"],
            ["mostRecentTrainingStatus", "trainingStatusFeedbackPhrase"],
            ["trainingStatus"],
            ["trainingStatusFeedbackPhrase"],
        ],
    )
    return (
        f"Training status: {_humanize_status(status)}."
        if status
        else "Training status: available, no summary fields found."
    )


def _vo2_line(data: Any) -> str:
    value = _vo2_value(data)
    if value is None:
        return "VO2 max: unavailable."
    source_date = data.get("_source_date") if isinstance(data, dict) else None
    if source_date:
        return f"VO2 max: latest from {source_date}: {value:.1f}."
    return f"VO2 max: {value:.1f}."


def _sleep_seconds(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    sleep = data.get("dailySleepDTO") if isinstance(data.get("dailySleepDTO"), dict) else data
    seconds = _first_number(
        sleep,
        ["sleepTimeSeconds", "sleepTimeInSeconds", "measurableAsleepDuration", "duration"],
    )
    if seconds is None:
        sleep_stage_seconds = [
            _first_number(sleep, [key])
            for key in ["deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds"]
        ]
        if any(value is not None for value in sleep_stage_seconds):
            seconds = sum(value or 0 for value in sleep_stage_seconds)
    return seconds


def _vo2_value(data: Any) -> float | None:
    if isinstance(data, list):
        data = _latest_dict(data)
    if isinstance(data, dict) and isinstance(data.get("values"), list):
        data = _latest_dict(data["values"])
    if not isinstance(data, dict):
        return None
    value = _nested_first(
        data,
        [
            ["generic", "vo2MaxPreciseValue"],
            ["generic", "vo2MaxValue"],
            ["vo2MaxPreciseValue"],
            ["vo2MaxValue"],
        ],
    )
    return float(value) if isinstance(value, NUMERIC_TYPES) else None


def _body_battery_low(data: Any, stats: Any) -> float | None:
    if isinstance(stats, dict):
        low = _first_number(stats, ["bodyBatteryLowestValue"])
        if low is not None:
            return low
    if not isinstance(data, list):
        return None
    values = []
    for day in data:
        if isinstance(day, dict):
            values.extend(day.get("bodyBatteryValuesArray") or [])
    scores = [
        row[1]
        for row in values
        if isinstance(row, list) and len(row) >= 2 and isinstance(row[1], NUMERIC_TYPES)
    ]
    return min(scores) if scores else None


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes:02d}m"


def _first_number(data: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, NUMERIC_TYPES):
            return float(value)
    return None


def _first_string(data: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _nested_first(data: dict[str, Any], paths: list[list[str]]) -> Any:
    for path in paths:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if current is not None and current != "":
            return current
    return None


def _latest_dict(items: list[Any]) -> dict[str, Any]:
    dicts = [item for item in items if isinstance(item, dict)]
    if not dicts:
        return {}
    return sorted(
        dicts,
        key=lambda item: str(
            item.get("timestampLocal")
            or item.get("timestamp")
            or item.get("calendarDate")
            or item.get("date")
            or ""
        ),
    )[-1]


def _humanize_status(value: Any) -> str:
    if not isinstance(value, str):
        return str(value)
    return value.replace("_", " ").title()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _typical_range(values: list[float]) -> tuple[float, float]:
    if len(values) < 5:
        return min(values), max(values)
    return _percentile(values, 0.10), _percentile(values, 0.90)


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * proportion
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _format_number(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"
