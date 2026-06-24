from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import time as datetime_time
from typing import Any, Callable

from .activity_format import detailed_activity_context, recent_runs_context
from .athlete_profile import append_coaching_preference, athlete_profile_context
from .coach_log import append_run_result
from .coach_reflection import generate_coach_reflection
from .coach_time import coach_now, coach_today
from .daily_checkin import (
    current_garmin_context,
    daily_workout_checkin,
    has_completed_run_for_date,
    has_planned_workout_for_date,
    mark_daily_checkin_sent,
    should_send_daily_checkin,
)
from .debug_context import build_chat_debug_context, format_chat_debug_context
from .evening_report import (
    end_of_day_report,
    mark_evening_report_sent,
    should_send_evening_report,
)
from .event_log import log_event, start_trace
from .feedback import summarize_training
from .garmin_cache import refresh_garmin_snapshots
from .garmin_context import safe_garmin_weekly_context
from .goal_readiness import goal_readiness_context
from .goal_store import save_training_goal, training_goal_context
from .heart_rate import observed_max_heart_rate
from .openai_client import (
    coaching_reply,
    image_coaching_reply,
    normalize_post_run_feedback,
    resolve_pending_question,
)
from .plan_store import save_weekly_plan, weekly_plan_context, weekly_plan_context_for_date
from .plan_suggestion import (
    mark_sunday_plan_sent,
    next_week_start,
    should_send_sunday_plan,
    suggest_next_week_plan,
)
from .post_run_feedback import append_post_run_feedback, inferred_post_run_feedback
from .run_summary import run_summary_for_date
from .strava_client import StravaClient
from .strava_sync import save_synced_run_detail, sync_strava_runs
from .weather_client import safe_enrich_activity_weather
from .weekly_review import current_week_start, weekly_coaching_message

DEFAULT_LOOKBACK_DAYS = 28
GARMIN_REFRESH_TIME = datetime_time(5, 0)
COACH_REFLECTION_REFRESH_TIME = datetime_time(19, 0)
STRAVA_RECENT_REFRESH_DAYS = 1


@dataclass(frozen=True)
class Command:
    names: tuple[str, ...]
    help_text: str
    handler_name: str
    show_in_help: bool = True
    usage: str | None = None


COMMANDS = (
    Command(("/start",), "show this help", "_help_command", show_in_help=False),
    Command(("/help",), "show this help", "_help_command"),
    Command(("/ping",), "respond with Pong!", "_ping_command"),
    Command(("/recent", "/summary"), "summarize recent training", "_recent_command"),
    Command(
        ("/last", "/last_run"),
        "send a workout summary for the latest Strava run",
        "_last_command",
        show_in_help=False,
    ),
    Command(
        ("/run",),
        "send a workout summary for a specific day",
        "_run_command",
        show_in_help=False,
        usage="/run YYYY-MM-DD",
    ),
    Command(
        ("/suggestplan",),
        "suggest a plan idea for next week",
        "_suggest_plan_command",
        show_in_help=False,
    ),
    Command(("/plan",), "show the current weekly plan", "_plan_command"),
    Command(
        ("/setplan",),
        "save this week's plan",
        "_set_plan_command",
        show_in_help=False,
        usage="/setplan <plan>",
    ),
    Command(("/goal",), "show the current overall training goal", "_goal_command"),
    Command(
        ("/setgoal",),
        "save your overall training goal",
        "_set_goal_command",
        show_in_help=False,
        usage="/setgoal <goal>",
    ),
    Command(("/preferences", "/profile"), "show remembered coaching notes", "_profile_command"),
    Command(
        ("/preference", "/note"),
        "explicitly save a coaching note",
        "_note_command",
        show_in_help=False,
        usage="/preference <note>",
    ),
    Command(
        ("/feedback",),
        "save post-run RPE and feel",
        "_feedback_command",
        show_in_help=False,
        usage="/feedback RPE 6, legs heavy, pain none, notes faded late",
    ),
    Command(
        ("/garmin",),
        "show today's Garmin readiness context",
        "_garmin_command",
        show_in_help=False,
    ),
    Command(
        ("/garminweek", "/garmin-week"),
        "show recent Garmin recovery trend",
        "_garmin_week_command",
        show_in_help=False,
    ),
    Command(("/check",), "check Strava for newly synced runs", "_check_command"),
    Command(("/tick",), "run scheduled checks now", "_tick_command", show_in_help=False),
)
COMMAND_BY_NAME = {name: command for command in COMMANDS for name in command.names}


class CoachAgent:
    def __init__(
        self,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        strava_client: StravaClient | None = None,
        state: dict[str, Any] | None = None,
        save_state: Callable[[], None] | None = None,
    ):
        self.lookback_days = lookback_days
        self.strava = strava_client or StravaClient()
        self.state = state if state is not None else {}
        self._save_state = save_state or (lambda: None)
        self.conversation: list[dict[str, str]] = []

    def handle_message(self, text: str, source: str = "coach") -> list[str]:
        text = text.strip()
        if not text:
            return []
        command = text.split()[0].lower()
        trace = start_trace(
            source=source,
            interaction="message",
            command=command,
            chars=len(text),
        )
        log_event("debug", {"message": "coach_handle_message_start", "command": command})
        status = "ok"
        replies: list[str] = []
        try:
            replies = self._handle_message(text, command)
        except RuntimeError as error:
            status = "error"
            replies = [f"Something failed while coaching: {error}"]
            trace.add(error=repr(error))
        except Exception as error:
            status = "error"
            trace.add(error=repr(error))
            raise
        finally:
            log_event("debug", {"message": "coach_handle_message_done", "command": command})
            trace.close(status=status, reply_count=len(replies))
        return replies

    def tick(self, source: str = "scheduler") -> list[str]:
        trace = start_trace(source=source, interaction="tick")
        messages: list[str] = []
        status = "ok"
        try:
            self.refresh_recent_strava_summaries_if_due()
            self.refresh_garmin_cache_if_due()
            self.refresh_coach_reflection_if_due()
            daily = self.daily_checkin_if_due()
            if daily:
                messages.append(daily)
            sunday = self.sunday_plan_if_due()
            if sunday:
                messages.append(sunday)
            evening = self.evening_report_if_due()
            if evening:
                messages.append(evening)
            return messages
        except Exception as error:
            status = "error"
            trace.add(error=repr(error))
            raise
        finally:
            trace.close(status=status, message_count=len(messages))

    def seed_seen_activities(self) -> None:
        if self.state.get("seen_activity_ids"):
            return
        log_event("debug", {"message": "seed_seen_activities_start"})
        activities = self.strava.recent_activities(days=self.lookback_days)
        log_event("debug", {"message": "seed_seen_activities_done", "count": len(activities)})
        self.state["seen_activity_ids"] = [
            activity["id"] for activity in activities if "id" in activity
        ]
        self._save_state()

    def _handle_message(self, text: str, command: str) -> list[str]:
        command_spec = COMMAND_BY_NAME.get(command)
        if command_spec:
            handler = getattr(self, command_spec.handler_name)
            return handler(text, command)
        pending_reply = self._pending_question_reply_or_none(text)
        if pending_reply:
            return [pending_reply]
        return [self.coach_reply(text)]

    def _help_command(self, _text: str, _command: str) -> list[str]:
        return [help_text()]

    def _ping_command(self, _text: str, _command: str) -> list[str]:
        return ["Pong!"]

    def _recent_command(self, _text: str, _command: str) -> list[str]:
        return [self.training_summary()]

    def _last_command(self, _text: str, _command: str) -> list[str]:
        return [self.last_run_summary()]

    def _run_command(self, text: str, _command: str) -> list[str]:
        return [self._run_summary_from_message(text)]

    def _suggest_plan_command(self, _text: str, _command: str) -> list[str]:
        return [self.next_week_plan()]

    def _plan_command(self, _text: str, _command: str) -> list[str]:
        return [weekly_plan_context()]

    def _set_plan_command(self, text: str, _command: str) -> list[str]:
        return [self._set_weekly_plan_from_message(text)]

    def _goal_command(self, _text: str, _command: str) -> list[str]:
        return [training_goal_context()]

    def _set_goal_command(self, text: str, _command: str) -> list[str]:
        return [self._set_training_goal_from_message(text)]

    def _profile_command(self, _text: str, _command: str) -> list[str]:
        return [athlete_profile_context()]

    def _note_command(self, text: str, command: str) -> list[str]:
        return [self._save_coaching_preference_from_message(text, command)]

    def _feedback_command(self, text: str, _command: str) -> list[str]:
        return [self._save_post_run_feedback_from_message(text)]

    def _garmin_command(self, _text: str, _command: str) -> list[str]:
        return [current_garmin_context()]

    def _garmin_week_command(self, _text: str, _command: str) -> list[str]:
        return [safe_garmin_weekly_context(days=7)]

    def _check_command(self, _text: str, _command: str) -> list[str]:
        return self.check_new_runs(force=True)

    def _tick_command(self, _text: str, _command: str) -> list[str]:
        messages = self.tick()
        return messages or ["No scheduled messages due."]

    def coach_reply(self, text: str) -> str:
        log_event("debug", {"message": "coach_reply_recent_activities_start"})
        activities = self.strava.recent_activities(days=self.lookback_days)
        log_event(
            "debug",
            {"message": "coach_reply_recent_activities_done", "count": len(activities)},
        )
        summary = summarize_training(activities, days=self.lookback_days)
        log_event("debug", {"message": "coach_reply_openai_start"})
        reply = coaching_reply(
            text,
            training_summary=summary,
            recent_runs=recent_runs_context(activities),
            weekly_plan=weekly_plan_context_for_date(coach_today()),
            training_goal=training_goal_context(),
            goal_readiness=goal_readiness_context(
                activities=activities,
                days=self.lookback_days,
            ),
            conversation=self.conversation,
        )
        log_event("debug", {"message": "coach_reply_openai_done", "chars": len(reply)})
        self.conversation.extend(
            [
                {"role": "athlete", "content": text},
                {"role": "coach", "content": reply},
            ]
        )
        self.conversation = self.conversation[-12:]
        return reply

    def coach_image_reply(self, caption: str, image_bytes: bytes, mime_type: str) -> str:
        message = caption.strip() or (
            "The athlete sent an image for coaching context. Inspect it and explain the "
            "running implications."
        )
        log_event("debug", {"message": "coach_image_recent_activities_start"})
        activities = self.strava.recent_activities(days=self.lookback_days)
        log_event(
            "debug",
            {"message": "coach_image_recent_activities_done", "count": len(activities)},
        )
        summary = summarize_training(activities, days=self.lookback_days)
        log_event("debug", {"message": "coach_image_openai_start", "chars": len(image_bytes)})
        reply = image_coaching_reply(
            message,
            image_bytes=image_bytes,
            mime_type=mime_type,
            training_summary=summary,
            recent_runs=recent_runs_context(activities),
            weekly_plan=weekly_plan_context_for_date(coach_today()),
            training_goal=training_goal_context(),
            conversation=self.conversation,
        )
        log_event("debug", {"message": "coach_image_openai_done", "chars": len(reply)})
        self.conversation.extend(
            [
                {"role": "athlete", "content": f"[image] {message}"},
                {"role": "coach", "content": reply},
            ]
        )
        self.conversation = self.conversation[-12:]
        return reply

    def debug_context(self, text: str) -> str:
        context = build_chat_debug_context(
            message=text,
            client=self.strava,
            lookback_days=self.lookback_days,
            conversation=self.conversation,
            tools_enabled=True,
        )
        return format_chat_debug_context(context)

    def training_summary(self) -> str:
        log_event("debug", {"message": "training_summary_recent_activities_start"})
        activities = self.strava.recent_activities(days=self.lookback_days)
        log_event(
            "debug",
            {"message": "training_summary_recent_activities_done", "count": len(activities)},
        )
        return summarize_training(activities, days=self.lookback_days)

    def last_run_summary(self) -> str:
        log_event("debug", {"message": "last_run_recent_activities_start"})
        activities = self.strava.recent_activities(days=max(self.lookback_days, 90))
        log_event("debug", {"message": "last_run_recent_activities_done", "count": len(activities)})
        log_event("debug", {"message": "last_run_lookup_start"})
        last_run = self.strava.latest_run(days=max(self.lookback_days, 90))
        log_event("debug", {"message": "last_run_lookup_done", "found": bool(last_run)})
        if not last_run:
            return "No recent Strava runs found."
        log_event(
            "debug",
            {"message": "last_run_detail_start", "activity_id": last_run.get("id")},
        )
        detailed_run = self.strava.detailed_activity(last_run["id"])
        detailed_run = safe_enrich_activity_weather(detailed_run)
        log_event(
            "debug",
            {"message": "last_run_detail_done", "activity_id": last_run.get("id")},
        )

        prompt = (
            "Write a natural post-run coaching text for Telegram about this athlete's most "
            "recent Strava run. Do not use a title, header, markdown, or label-style opener. "
            "Start like a coach reacting to the workout, with the core run facts woven into "
            "the first sentence. Use lap-by-lap data to identify workout structure and pacing, "
            "compare against the matching weekly plan day when available, and give one practical "
            "next step. Keep it concise and conversational."
        )
        try:
            log_event("debug", {"message": "last_run_openai_start"})
            note = coaching_reply(
                prompt,
                training_summary=summarize_training(activities, days=self.lookback_days),
                recent_runs=detailed_activity_context(
                    detailed_run,
                    target_date=_activity_date(detailed_run),
                    max_heart_rate=observed_max_heart_rate([*activities, detailed_run]),
                ),
                weekly_plan=weekly_plan_context_for_date(_activity_date(detailed_run)),
                training_goal=training_goal_context(),
                garmin_context=current_garmin_context(),
                conversation=self.conversation,
                tools_enabled=False,
            )
            log_event("debug", {"message": "last_run_openai_done", "chars": len(note)})
        except RuntimeError as error:
            note = _last_run_fallback_note(last_run, error)
        return note

    def run_summary_for_date(self, date_text: str, search_days: int = 120) -> str:
        target_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        log_event("debug", {"message": "run_summary_start", "date": date_text})
        summary = run_summary_for_date(
            self.strava,
            target_date,
            search_days=search_days,
            lookback_days=self.lookback_days,
        )
        log_event("debug", {"message": "run_summary_done", "date": date_text})
        return summary

    def next_week_plan(self) -> str:
        target_week_start = next_week_start(coach_today())
        log_event(
            "debug",
            {"message": "suggest_plan_start", "week_start": target_week_start.isoformat()},
        )
        plan = suggest_next_week_plan(
            self.strava,
            target_week_start=target_week_start,
            lookback_days=max(self.lookback_days, 42),
        )
        log_event(
            "debug",
            {"message": "suggest_plan_done", "week_start": target_week_start.isoformat()},
        )
        return plan

    def sunday_plan_if_due(self) -> str | None:
        now = coach_now()
        if not should_send_sunday_plan(now, self.state):
            return None

        target_week_start = next_week_start(now.date())
        log_event(
            "debug",
            {"message": "sunday_plan_start", "week_start": target_week_start.isoformat()},
        )
        try:
            message = weekly_coaching_message(
                self.strava,
                week_start=current_week_start(now.date()),
                target_week_start=target_week_start,
                lookback_days=max(self.lookback_days, 42),
            )
        except RuntimeError as error:
            self.state["last_sunday_plan_error"] = str(error)
            log_event(
                "debug",
                {
                    "message": "sunday_plan_failed",
                    "week_start": target_week_start.isoformat(),
                    "error": str(error),
                },
            )
            self._save_state()
            return None
        log_event(
            "debug",
            {"message": "sunday_plan_done", "week_start": target_week_start.isoformat()},
        )
        self.state.pop("last_sunday_plan_error", None)
        mark_sunday_plan_sent(now, self.state)
        self._save_state()
        return message

    def refresh_coach_reflection_if_due(self) -> None:
        now = coach_now()
        if now.time() < COACH_REFLECTION_REFRESH_TIME:
            return
        today = now.date().isoformat()
        if self.state.get("last_coach_reflection_attempt_date") == today:
            return

        log_event("debug", {"message": "coach_reflection_start", "trigger": "daily"})
        self.state["last_coach_reflection_attempt_date"] = today
        try:
            generate_coach_reflection(self.strava, lookback_days=max(self.lookback_days, 42))
        except RuntimeError as error:
            self.state["last_coach_reflection_error"] = str(error)
            log_event(
                "debug",
                {
                    "message": "coach_reflection_failed",
                    "trigger": "daily",
                    "error": str(error),
                },
            )
        else:
            self.state["last_coach_reflection_date"] = today
            self.state.pop("last_coach_reflection_error", None)
            log_event("debug", {"message": "coach_reflection_done", "trigger": "daily"})
        self._save_state()

    def daily_checkin_if_due(self) -> str | None:
        now = coach_now()
        if not should_send_daily_checkin(now, self.state):
            return None
        if not has_planned_workout_for_date(now.date()):
            log_event(
                "debug",
                {"message": "daily_checkin_skipped_no_plan", "date": now.date().isoformat()},
            )
            mark_daily_checkin_sent(now, self.state)
            self._save_state()
            return None
        if has_completed_run_for_date(self.strava, now.date()):
            log_event(
                "debug",
                {"message": "daily_checkin_skipped_run_completed", "date": now.date().isoformat()},
            )
            mark_daily_checkin_sent(now, self.state)
            self._save_state()
            return None

        log_event("debug", {"message": "daily_checkin_start", "date": now.date().isoformat()})
        try:
            checkin = daily_workout_checkin(self.strava, target_date=now.date(), lookback_days=7)
        except RuntimeError as error:
            self.state["last_daily_checkin_error"] = str(error)
            log_event(
                "debug",
                {
                    "message": "daily_checkin_failed",
                    "date": now.date().isoformat(),
                    "error": str(error),
                },
            )
            self._save_state()
            return None
        log_event("debug", {"message": "daily_checkin_done", "date": now.date().isoformat()})
        self.state.pop("last_daily_checkin_error", None)
        mark_daily_checkin_sent(now, self.state)
        self._save_state()
        return checkin

    def evening_report_if_due(self) -> str | None:
        now = coach_now()
        if not should_send_evening_report(now, self.state):
            return None
        if not has_completed_run_for_date(self.strava, now.date()):
            log_event(
                "debug",
                {"message": "evening_report_skipped_no_run", "date": now.date().isoformat()},
            )
            mark_evening_report_sent(now, self.state)
            self._save_state()
            return None

        log_event("debug", {"message": "evening_report_start", "date": now.date().isoformat()})
        try:
            report = end_of_day_report(self.strava, target_date=now.date(), lookback_days=7)
        except RuntimeError as error:
            self.state["last_evening_report_error"] = str(error)
            log_event(
                "debug",
                {
                    "message": "evening_report_failed",
                    "date": now.date().isoformat(),
                    "error": str(error),
                },
            )
            self._save_state()
            return None
        log_event("debug", {"message": "evening_report_done", "date": now.date().isoformat()})
        self.state.pop("last_evening_report_error", None)
        mark_evening_report_sent(now, self.state)
        self._save_state()
        return report

    def refresh_recent_strava_summaries_if_due(self) -> None:
        now = coach_now()
        hour_key = now.strftime("%Y-%m-%dT%H")
        if self.state.get("last_strava_recent_refresh_hour") == hour_key:
            return

        log_event("debug", {"message": "strava_recent_refresh_start", "hour": hour_key})
        try:
            result = sync_strava_runs(self.strava, days=STRAVA_RECENT_REFRESH_DAYS)
        except RuntimeError as error:
            self.state["last_strava_recent_refresh_error"] = str(error)
            log_event(
                "debug",
                {
                    "message": "strava_recent_refresh_failed",
                    "hour": hour_key,
                    "error": str(error),
                },
            )
            self._save_state()
            return

        self.state["last_strava_recent_refresh_hour"] = hour_key
        self.state.pop("last_strava_recent_refresh_error", None)
        log_event(
            "debug",
            {
                "message": "strava_recent_refresh_done",
                "hour": hour_key,
                "runs_seen": result.get("runs_seen"),
                "summaries_saved": result.get("summaries_saved"),
                "details_fetched": result.get("details_fetched"),
            },
        )
        self._save_state()

    def refresh_garmin_cache_if_due(self) -> None:
        now = coach_now()
        if now.time() < GARMIN_REFRESH_TIME:
            return
        today = now.date().isoformat()
        if self.state.get("last_garmin_refresh_attempt_date") == today:
            return

        log_event("debug", {"message": "garmin_refresh_start", "date": today})
        self.state["last_garmin_refresh_attempt_date"] = today
        try:
            refresh_garmin_snapshots(days=45)
        except RuntimeError as error:
            self.state["last_garmin_refresh_error"] = str(error)
            log_event("debug", {"message": "garmin_refresh_failed", "error": str(error)})
        else:
            self.state["last_garmin_refresh_date"] = today
            self.state.pop("last_garmin_refresh_error", None)
            log_event("debug", {"message": "garmin_refresh_done", "date": today})
        self._save_state()

    def check_new_runs(self, force: bool = False) -> list[str]:
        log_event("debug", {"message": "notify_new_runs_start", "forced": force})
        activities = self.strava.recent_activities(days=self.lookback_days)
        seen = set(self.state.get("seen_activity_ids", []))
        new_runs = [
            activity
            for activity in activities
            if activity.get("type") == "Run" and activity.get("id") not in seen
        ]
        self.state["seen_activity_ids"] = [
            activity["id"] for activity in activities if "id" in activity
        ]
        self._save_state()
        log_event(
            "debug",
            {
                "message": "notify_new_runs_done",
                "activity_count": len(activities),
                "new_run_count": len(new_runs),
            },
        )

        if not new_runs:
            return ["No new Strava runs since my last check."] if force else []

        messages = []
        for run in reversed(new_runs):
            log_event("debug", {"message": "new_run_detail_start", "activity_id": run.get("id")})
            detailed_run = self.strava.detailed_activity(run["id"])
            detailed_run = safe_enrich_activity_weather(detailed_run)
            log_event("debug", {"message": "new_run_detail_done", "activity_id": run.get("id")})
            save_synced_run_detail(run, detailed_run)
            append_run_result(detailed_run)
            prompt = (
                "A new Strava run just synced. Write a natural post-run coaching text for "
                "Telegram. Do not use a title, header, markdown, or label-style opener like "
                "'New run synced.' Start like a coach reacting to the workout, with the core "
                "run facts woven into the first sentence. Include one thing that went well and "
                "one sensible next step. Use the lap-by-lap data when it is present."
            )
            summary = summarize_training(activities, days=self.lookback_days)
            log_event("debug", {"message": "new_run_openai_start", "activity_id": run.get("id")})
            note = coaching_reply(
                prompt,
                training_summary=summary,
                recent_runs=detailed_activity_context(
                    detailed_run,
                    target_date=_activity_date(detailed_run),
                    max_heart_rate=observed_max_heart_rate([*activities, detailed_run]),
                ),
                weekly_plan=weekly_plan_context_for_date(_activity_date(detailed_run)),
                training_goal=training_goal_context(),
                garmin_context=current_garmin_context(),
                conversation=self.conversation,
                tools_enabled=False,
            )
            log_event("debug", {"message": "new_run_openai_done", "activity_id": run.get("id")})
            self._set_pending_post_run_feedback(
                activity_id=detailed_run.get("id") or run.get("id"),
                run_date=_activity_date(detailed_run).isoformat(),
            )
            self._save_state()
            messages.append(note + "\n\n" + _post_run_feedback_prompt())
        return messages

    def _run_summary_from_message(self, text: str) -> str:
        date_text = text[len("/run") :].strip()
        if not date_text:
            return "Send a date like:\n/run 2026-05-27"
        return self.run_summary_for_date(date_text)

    def _set_weekly_plan_from_message(self, text: str) -> str:
        plan_text = text[len("/setplan") :].strip()
        if not plan_text.strip():
            return "Send the plan after the command, like:\n/setplan\nMon easy 5\nTue workout"
        save_weekly_plan(plan_text)
        return "Saved this week's plan. I will use it in coaching."

    def _set_training_goal_from_message(self, text: str) -> str:
        goal_text = text[len("/setgoal") :].strip()
        if not goal_text.strip():
            return (
                "Send the goal after the command, like:\n"
                "/setgoal Boston Marathon on Oct 12, target 3:20, stay healthy."
            )
        save_training_goal(goal_text)
        return "Saved your training goal. I will use it in coaching."

    def _save_coaching_preference_from_message(self, text: str, command: str) -> str:
        preference_text = text[len(command) :].strip()
        if not preference_text:
            return (
                "Send the coaching preference after the command, like:\n"
                "/preference I prefer workouts by effort when Garmin readiness is low."
            )
        append_coaching_preference(preference_text)
        return "Saved that coaching preference. I will use it in future coaching."

    def _save_post_run_feedback_from_message(self, text: str) -> str:
        feedback_text = text[len("/feedback") :].strip()
        if not feedback_text:
            return "Send post-run feedback like:\n" "RPE 6, legs heavy, no pain, faded late"
        return self._save_post_run_feedback_from_text(feedback_text)

    def _save_post_run_feedback_from_text(self, feedback_text: str) -> str:
        try:
            normalized = normalize_post_run_feedback(feedback_text)
        except RuntimeError:
            normalized = {"is_feedback": True, "notes": feedback_text}
        if not normalized.get("is_feedback"):
            normalized = {"is_feedback": True, "notes": feedback_text}
        return self._save_normalized_post_run_feedback(feedback_text, normalized)

    def _pending_question_reply_or_none(self, text: str) -> str | None:
        pending = self._pending_question()
        if not pending:
            return None
        if pending.get("kind") != "post_run_feedback":
            return None
        return self._post_run_feedback_reply_or_none(text, pending=pending)

    def _post_run_feedback_reply_or_none(
        self,
        feedback_text: str,
        *,
        pending: dict[str, Any] | None = None,
    ) -> str | None:
        pending = pending or self._pending_question()
        try:
            resolution = resolve_pending_question(
                question=str((pending or {}).get("question") or _post_run_feedback_prompt()),
                response=feedback_text,
                kind="post_run_feedback",
            )
        except RuntimeError:
            resolution = {"answers_question": False, "extracted": {}}
        normalized = dict(resolution.get("extracted") or {})
        if not resolution.get("answers_question") or not normalized.get("is_feedback"):
            normalized = inferred_post_run_feedback(feedback_text)
        if not normalized.get("is_feedback"):
            return None
        return self._save_normalized_post_run_feedback(feedback_text, normalized, pending=pending)

    def _save_normalized_post_run_feedback(
        self,
        feedback_text: str,
        normalized: dict[str, Any],
        *,
        pending: dict[str, Any] | None = None,
    ) -> str:
        pending = pending or self._pending_question() or {}
        entry = append_post_run_feedback(
            feedback_text,
            normalized=normalized,
            activity_id=pending.get("activity_id"),
            run_date=pending.get("run_date"),
        )
        self.state.pop("pending_question", None)
        self.state.pop("pending_post_run_feedback", None)
        self._save_state()
        details = []
        if entry.get("rpe") is not None:
            details.append(f"RPE {entry['rpe']}")
        if entry.get("legs"):
            details.append(f"legs {entry['legs']}")
        if entry.get("pain"):
            details.append(f"pain {entry['pain']}")
        saved = ", ".join(details) if details else "I saved that note"
        follow_up = _post_run_feedback_follow_up(entry)
        return f"Got it. {saved}. {follow_up}"

    def _pending_question(self) -> dict[str, Any] | None:
        pending = self.state.get("pending_question")
        if isinstance(pending, dict) and pending.get("kind"):
            return pending
        legacy = self.state.get("pending_post_run_feedback")
        if isinstance(legacy, dict):
            return {
                "kind": "post_run_feedback",
                "question": _post_run_feedback_prompt(),
                "activity_id": legacy.get("activity_id"),
                "run_date": legacy.get("run_date"),
            }
        return None

    def _set_pending_post_run_feedback(self, *, activity_id: Any, run_date: str) -> None:
        self.state["pending_question"] = {
            "kind": "post_run_feedback",
            "question": _post_run_feedback_prompt(),
            "activity_id": activity_id,
            "run_date": run_date,
            "asked_at": coach_now().isoformat(),
        }
        self.state.pop("pending_post_run_feedback", None)


def help_text() -> str:
    command_lines = [
        f"{command.usage or command.names[0]} - {command.help_text}"
        for command in COMMANDS
        if command.show_in_help
    ]
    return (
        "Send me any running question and I will answer using your recent Strava context.\n\n"
        "Commands:\n" + "\n".join(command_lines) + "\n\n"
        "You can also say things like 'remember that I prefer long runs on Saturday' and I will "
        "decide whether to save that as future coaching context. If you state a durable race "
        "goal or target time, I can update the saved goal too."
    )


def _last_run_fallback_note(run: dict[str, Any], error: RuntimeError) -> str:
    distance_note = "Treat this as one data point in the larger training pattern."
    distance = float(run.get("distance") or 0)
    moving_time = int(run.get("moving_time") or run.get("elapsed_time") or 0)
    if distance > 0 and moving_time > 0:
        distance_note = (
            "The useful demo read: log the effort, compare how it felt against the pace, "
            "and keep the next run easy if there is lingering fatigue."
        )
    return (
        f"AI coaching was unavailable ({error}).\n\n"
        f"{distance_note}\n"
        "Next step: recover well today, then use the next easy run to confirm the legs are ready "
        "before adding intensity."
    )


def _post_run_feedback_prompt() -> str:
    return (
        "How did that run feel? Any pain or soreness? A quick reply like "
        "'RPE 6, legs normal, no pain' is enough."
    )


def _post_run_feedback_follow_up(entry: dict[str, Any]) -> str:
    rpe = entry.get("rpe")
    pain = str(entry.get("pain") or "").lower()
    legs = str(entry.get("legs") or "").lower()
    if pain and pain not in {"none", "no"}:
        return "That matters more than the splits; keep the next run easy and stop if it changes your stride."
    if isinstance(rpe, int) and rpe >= 8:
        return "That is a high effort signal, so I will treat the session as a bigger stressor than pace alone suggests."
    if legs in {"heavy", "dead", "sore", "tired"}:
        return "I will read that as fatigue context when judging the next couple of days."
    if isinstance(rpe, int) and rpe <= 4 and (not pain or pain in {"none", "no"}):
        return "That is a good sign that the work stayed controlled."
    return "I will use that with the pace and Garmin context next time."


def _activity_date(activity: dict[str, Any]):
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return coach_today()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return coach_today()
