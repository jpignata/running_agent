from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from .coach_time import COACH_TIME_ZONE, coach_today
from .daily_checkin import (
    DAILY_CHECKIN_STATE_KEY,
    daily_workout_checkin,
    has_completed_run_for_date,
    has_planned_workout_for_date,
)
from .evening_report import (
    EVENING_REPORT_STATE_KEY,
    EVENING_REPORT_TIME,
    end_of_day_report,
)
from .plan_suggestion import PLAN_STATE_KEY, SUNDAY, SUNDAY_PLAN_HOUR, next_week_start
from .strava_client import StravaClient
from .weekly_review import current_week_start, weekly_coaching_message


@dataclass(frozen=True)
class ScheduledPreview:
    kind: str
    target_date: date
    would_send: bool
    skip_reasons: list[str]
    tools_enabled: bool
    data_sources: list[str]
    message: str


def preview_scheduled_message(
    kind: str,
    *,
    client: StravaClient,
    target_date: date | None = None,
    state: dict[str, Any] | None = None,
) -> ScheduledPreview:
    state = state or {}
    target_date = target_date or coach_today()
    if kind == "morning":
        return _preview_morning(client, target_date, state)
    if kind == "evening":
        return _preview_evening(client, target_date, state)
    if kind == "weekly":
        return _preview_weekly(client, target_date, state)
    raise RuntimeError(f"Unknown scheduled preview kind: {kind}")


def format_scheduled_preview(preview: ScheduledPreview) -> str:
    reasons = ", ".join(preview.skip_reasons) if preview.skip_reasons else "none"
    return "\n\n".join(
        [
            "Scheduled message preview",
            f"Kind: {preview.kind}",
            f"Date: {preview.target_date.isoformat()}",
            f"Would normally send: {'yes' if preview.would_send else 'no'}",
            f"Skip reasons: {reasons}",
            f"Tools enabled: {'yes' if preview.tools_enabled else 'no'}",
            "Data sources: " + ", ".join(preview.data_sources),
            "Message:",
            preview.message,
        ]
    )


def _preview_morning(
    client: StravaClient,
    target_date: date,
    state: dict[str, Any],
) -> ScheduledPreview:
    skip_reasons = []
    if state.get(DAILY_CHECKIN_STATE_KEY) == target_date.isoformat():
        skip_reasons.append("already sent for date")
    if not has_planned_workout_for_date(target_date):
        skip_reasons.append("no planned workout for date")
    if has_completed_run_for_date(client, target_date):
        skip_reasons.append("run already completed for date")

    return ScheduledPreview(
        kind="morning",
        target_date=target_date,
        would_send=not skip_reasons,
        skip_reasons=skip_reasons,
        tools_enabled=False,
        data_sources=[
            "recent Strava activities",
            "matched weekly plan",
            "Garmin readiness",
            "training goal",
            "coach log",
        ],
        message=daily_workout_checkin(client, target_date=target_date, lookback_days=7),
    )


def _preview_evening(
    client: StravaClient,
    target_date: date,
    state: dict[str, Any],
) -> ScheduledPreview:
    skip_reasons = []
    if _scheduled_datetime(target_date, EVENING_REPORT_TIME).weekday() == 6:
        skip_reasons.append("Sunday evening report suppressed")
    if state.get(EVENING_REPORT_STATE_KEY) == target_date.isoformat():
        skip_reasons.append("already sent for date")
    if not has_completed_run_for_date(client, target_date):
        skip_reasons.append("no completed run for date")

    return ScheduledPreview(
        kind="evening",
        target_date=target_date,
        would_send=not skip_reasons,
        skip_reasons=skip_reasons,
        tools_enabled=False,
        data_sources=[
            "recent Strava activities",
            "runs completed on date",
            "matched weekly plan",
            "remaining weekly plan",
            "Garmin readiness",
            "training goal",
            "coach log",
        ],
        message=end_of_day_report(client, target_date=target_date, lookback_days=7),
    )


def _preview_weekly(
    client: StravaClient,
    target_date: date,
    state: dict[str, Any],
) -> ScheduledPreview:
    skip_reasons = []
    target_week_start = next_week_start(target_date)
    if _scheduled_datetime(target_date, time(SUNDAY_PLAN_HOUR)).weekday() != SUNDAY:
        skip_reasons.append("not Sunday")
    if state.get(PLAN_STATE_KEY) == target_week_start.isoformat():
        skip_reasons.append("already sent for target week")

    return ScheduledPreview(
        kind="weekly",
        target_date=target_date,
        would_send=not skip_reasons,
        skip_reasons=skip_reasons,
        tools_enabled=False,
        data_sources=[
            "recent Strava activities",
            "weekly quality/long-run details",
            "weekly plan",
            "Garmin recovery trend",
            "training goal",
            "coach log",
        ],
        message=weekly_coaching_message(
            client,
            week_start=current_week_start(target_date),
            target_week_start=target_week_start,
            lookback_days=42,
            log_review=False,
        ),
    )


def _scheduled_datetime(target_date: date, scheduled_time: time) -> datetime:
    return datetime.combine(target_date, scheduled_time, tzinfo=COACH_TIME_ZONE)
