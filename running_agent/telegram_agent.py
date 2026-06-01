from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError

from .activity_format import detailed_activity_context, recent_runs_context
from .athlete_profile import (
    append_coaching_preference,
    athlete_profile_context,
)
from .auth import load_env_file, require_env
from .coach_log import append_run_result
from .coach_time import coach_now, coach_today
from .daily_checkin import (
    current_garmin_context,
    daily_workout_checkin,
    has_completed_run_for_date,
    has_planned_workout_for_date,
    mark_daily_checkin_sent,
    should_send_daily_checkin,
)
from .event_log import log_event
from .feedback import summarize_training
from .goal_store import save_training_goal, training_goal_context
from .openai_client import coaching_reply
from .plan_store import save_weekly_plan, weekly_plan_context, weekly_plan_context_for_date
from .plan_suggestion import (
    mark_sunday_plan_sent,
    next_week_start,
    should_send_sunday_plan,
    suggest_next_week_plan,
)
from .run_summary import run_summary_for_date
from .storage_paths import STATE_PATH, prepare_parent
from .strava_client import StravaClient
from .telegram_client import TelegramClient
from .weekly_review import current_week_start, weekly_coaching_message

DEFAULT_LOOKBACK_DAYS = 21
TRANSIENT_ERRORS = (
    TimeoutError,
    socket.timeout,
    ConnectionError,
    URLError,
)


class TelegramRunningAgent:
    def __init__(
        self,
        poll_seconds: int = 300,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        state_path: Path = STATE_PATH,
        strava_client: StravaClient | None = None,
        telegram_client: TelegramClient | None = None,
        allowed_chat_id: str | None = None,
    ):
        load_env_file()
        self.poll_seconds = poll_seconds
        self.lookback_days = lookback_days
        self.state_path = state_path
        self.state = _load_state(state_path)
        self.strava = strava_client or StravaClient()
        self.telegram = telegram_client or TelegramClient(require_env("TELEGRAM_BOT_TOKEN"))
        self.allowed_chat_id = (
            allowed_chat_id
            or os.environ.get("TELEGRAM_CHAT_ID")
            or self.state.get("telegram_chat_id")
        )
        self.conversation: list[dict[str, str]] = []

    def run_forever(self) -> None:
        self._seed_seen_activities()
        print("Running Telegram coach. Press Ctrl+C to stop.")
        next_strava_check = time.monotonic() + self.poll_seconds

        while True:
            try:
                self._handle_telegram_updates()
                self._send_daily_checkin_if_due()
                self._send_sunday_plan_if_due()
                if time.monotonic() >= next_strava_check:
                    self._notify_new_runs()
                    next_strava_check = time.monotonic() + self.poll_seconds
            except KeyboardInterrupt:
                raise
            except TRANSIENT_ERRORS as error:
                log_event("debug", {"message": "transient_loop_error", "error": repr(error)})
                time.sleep(5)

    def _handle_telegram_updates(self) -> None:
        offset = self.state.get("telegram_update_offset")
        log_event("debug", {"message": "telegram_get_updates_start", "offset": offset})
        updates = self.telegram.get_updates(offset=offset, timeout=25)
        log_event("debug", {"message": "telegram_get_updates_done", "count": len(updates)})
        for update in updates:
            self.state["telegram_update_offset"] = int(update["update_id"]) + 1
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if not text or chat_id is None:
                continue
            if not self._chat_allowed(chat_id):
                continue
            log_event("rx", {"chat_id": chat_id, "text": text})
            self._handle_message(chat_id, text)
        _save_state(self.state, self.state_path)

    def _chat_allowed(self, chat_id: int) -> bool:
        if self.allowed_chat_id and str(chat_id) != str(self.allowed_chat_id):
            return False
        if not self.allowed_chat_id:
            self.allowed_chat_id = str(chat_id)
            self.state["telegram_chat_id"] = str(chat_id)
            self._send_message(
                chat_id,
                "You are connected. I will use this Telegram chat for running-coach updates.",
            )
        return True

    def _handle_message(self, chat_id: int, text: str) -> None:
        command = text.split()[0].lower()
        log_event(
            "debug", {"message": "handle_message_start", "chat_id": chat_id, "command": command}
        )
        try:
            if command in {"/start", "/help"}:
                self._send_message(chat_id, _help_text())
            elif command == "/ping":
                self._send_message(chat_id, "Pong!")
            elif command in {"/recent", "/summary"}:
                self._send_message(chat_id, self._training_summary())
            elif command in {"/last", "/last_run"}:
                self.send_last_run_summary(chat_id=chat_id)
            elif command == "/run":
                self._send_run_summary_from_message(chat_id, text)
            elif command == "/suggestplan":
                self.send_next_week_plan(chat_id=chat_id)
            elif command == "/plan":
                self._send_message(chat_id, weekly_plan_context())
            elif command == "/setplan":
                self._set_weekly_plan_from_message(chat_id, text)
            elif command == "/goal":
                self._send_message(chat_id, training_goal_context())
            elif command == "/setgoal":
                self._set_training_goal_from_message(chat_id, text)
            elif command in {"/preferences", "/profile"}:
                self._send_message(chat_id, athlete_profile_context())
            elif command in {"/preference", "/note"}:
                self._save_coaching_preference_from_message(chat_id, text, command)
            elif command == "/check":
                self._notify_new_runs(force_chat_id=chat_id)
            else:
                self._send_message(chat_id, self._coach_reply(text))
        except RuntimeError as error:
            self._send_message(chat_id, f"Something failed while coaching: {error}")
        log_event(
            "debug", {"message": "handle_message_done", "chat_id": chat_id, "command": command}
        )

    def _send_message(self, chat_id: int | str, text: str) -> None:
        log_event(
            "debug", {"message": "telegram_send_start", "chat_id": chat_id, "chars": len(text)}
        )
        self.telegram.send_message(chat_id, text)
        log_event("tx", {"chat_id": chat_id, "text": text})
        log_event(
            "debug", {"message": "telegram_send_done", "chat_id": chat_id, "chars": len(text)}
        )

    def _coach_reply(self, text: str) -> str:
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
            weekly_plan=weekly_plan_context(),
            training_goal=training_goal_context(),
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

    def _training_summary(self) -> str:
        log_event("debug", {"message": "training_summary_recent_activities_start"})
        activities = self.strava.recent_activities(days=self.lookback_days)
        log_event(
            "debug",
            {"message": "training_summary_recent_activities_done", "count": len(activities)},
        )
        return summarize_training(activities, days=self.lookback_days)

    def send_last_run_summary(self, chat_id: int | str | None = None) -> None:
        target_chat_id = chat_id or self.allowed_chat_id
        if not target_chat_id:
            raise RuntimeError(
                "No Telegram chat is configured yet. Message the bot once, or set TELEGRAM_CHAT_ID."
            )

        log_event("debug", {"message": "last_run_recent_activities_start"})
        activities = self.strava.recent_activities(days=max(self.lookback_days, 90))
        log_event("debug", {"message": "last_run_recent_activities_done", "count": len(activities)})
        log_event("debug", {"message": "last_run_lookup_start"})
        last_run = self.strava.latest_run(days=max(self.lookback_days, 90))
        log_event("debug", {"message": "last_run_lookup_done", "found": bool(last_run)})
        if not last_run:
            self._send_message(target_chat_id, "No recent Strava runs found.")
            return
        log_event(
            "debug",
            {"message": "last_run_detail_start", "activity_id": last_run.get("id")},
        )
        detailed_run = self.strava.detailed_activity(last_run["id"])
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
                ),
                weekly_plan=weekly_plan_context_for_date(_activity_date(detailed_run)),
                training_goal=training_goal_context(),
                garmin_context=current_garmin_context(),
                conversation=self.conversation,
            )
            log_event("debug", {"message": "last_run_openai_done", "chars": len(note)})
        except RuntimeError as error:
            note = _last_run_fallback_note(last_run, error)
        self._send_message(target_chat_id, note)

    def send_run_summary_for_date(
        self,
        date_text: str,
        chat_id: int | str | None = None,
        search_days: int = 120,
    ) -> None:
        target_chat_id = chat_id or self.allowed_chat_id
        if not target_chat_id:
            raise RuntimeError(
                "No Telegram chat is configured yet. Message the bot once, or set TELEGRAM_CHAT_ID."
            )
        target_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        log_event(
            "debug",
            {"message": "run_summary_start", "chat_id": target_chat_id, "date": date_text},
        )
        summary = run_summary_for_date(
            self.strava,
            target_date,
            search_days=search_days,
            lookback_days=self.lookback_days,
        )
        log_event(
            "debug",
            {"message": "run_summary_done", "chat_id": target_chat_id, "date": date_text},
        )
        self._send_message(target_chat_id, summary)

    def send_next_week_plan(self, chat_id: int | str | None = None) -> None:
        target_chat_id = chat_id or self.allowed_chat_id
        if not target_chat_id:
            raise RuntimeError(
                "No Telegram chat is configured yet. Message the bot once, or set TELEGRAM_CHAT_ID."
            )
        target_week_start = next_week_start(coach_today())
        log_event(
            "debug",
            {
                "message": "suggest_plan_start",
                "chat_id": target_chat_id,
                "week_start": target_week_start.isoformat(),
            },
        )
        plan = suggest_next_week_plan(
            self.strava,
            target_week_start=target_week_start,
            lookback_days=max(self.lookback_days, 42),
        )
        log_event(
            "debug",
            {
                "message": "suggest_plan_done",
                "chat_id": target_chat_id,
                "week_start": target_week_start.isoformat(),
            },
        )
        self._send_message(target_chat_id, plan)

    def _send_run_summary_from_message(self, chat_id: int | str, text: str) -> None:
        date_text = text[len("/run") :].strip()
        if not date_text:
            self._send_message(chat_id, "Send a date like:\n/run 2026-05-27")
            return
        self.send_run_summary_for_date(date_text, chat_id=chat_id)

    def _set_weekly_plan_from_message(self, chat_id: int | str, text: str) -> None:
        plan_text = text[len("/setplan") :].strip()
        if not plan_text.strip():
            self._send_message(
                chat_id,
                "Send the plan after the command, like:\n/setplan\nMon easy 5\nTue workout",
            )
            return
        save_weekly_plan(plan_text)
        self._send_message(chat_id, "Saved this week's plan. I will use it in coaching.")

    def _set_training_goal_from_message(self, chat_id: int | str, text: str) -> None:
        goal_text = text[len("/setgoal") :].strip()
        if not goal_text.strip():
            self._send_message(
                chat_id,
                "Send the goal after the command, like:\n"
                "/setgoal Boston Marathon on Oct 12, target 3:20, stay healthy.",
            )
            return
        save_training_goal(goal_text)
        self._send_message(chat_id, "Saved your training goal. I will use it in coaching.")

    def _save_coaching_preference_from_message(
        self,
        chat_id: int | str,
        text: str,
        command: str,
    ) -> None:
        preference_text = text[len(command) :].strip()
        if not preference_text:
            self._send_message(
                chat_id,
                "Send the coaching preference after the command, like:\n"
                "/preference I prefer workouts by effort when Garmin readiness is low.",
            )
            return
        append_coaching_preference(preference_text)
        self._send_message(
            chat_id, "Saved that coaching preference. I will use it in future coaching."
        )

    def _send_sunday_plan_if_due(self) -> None:
        if not self.allowed_chat_id:
            return
        now = coach_now()
        if not should_send_sunday_plan(now, self.state):
            return

        target_week_start = next_week_start(now.date())
        log_event(
            "debug",
            {"message": "sunday_plan_start", "week_start": target_week_start.isoformat()},
        )
        message = weekly_coaching_message(
            self.strava,
            week_start=current_week_start(now.date()),
            target_week_start=target_week_start,
            lookback_days=max(self.lookback_days, 42),
        )
        log_event(
            "debug",
            {"message": "sunday_plan_done", "week_start": target_week_start.isoformat()},
        )
        self._send_message(self.allowed_chat_id, message)
        mark_sunday_plan_sent(now, self.state)
        _save_state(self.state, self.state_path)

    def _send_daily_checkin_if_due(self) -> None:
        if not self.allowed_chat_id:
            return
        now = coach_now()
        if not should_send_daily_checkin(now, self.state):
            return
        if not has_planned_workout_for_date(now.date()):
            log_event(
                "debug",
                {"message": "daily_checkin_skipped_no_plan", "date": now.date().isoformat()},
            )
            mark_daily_checkin_sent(now, self.state)
            _save_state(self.state, self.state_path)
            return
        if has_completed_run_for_date(self.strava, now.date()):
            log_event(
                "debug",
                {"message": "daily_checkin_skipped_run_completed", "date": now.date().isoformat()},
            )
            mark_daily_checkin_sent(now, self.state)
            _save_state(self.state, self.state_path)
            return

        log_event(
            "debug",
            {"message": "daily_checkin_start", "date": now.date().isoformat()},
        )
        checkin = daily_workout_checkin(
            self.strava,
            target_date=now.date(),
            lookback_days=7,
        )
        log_event(
            "debug",
            {"message": "daily_checkin_done", "date": now.date().isoformat()},
        )
        self._send_message(self.allowed_chat_id, checkin)
        mark_daily_checkin_sent(now, self.state)
        _save_state(self.state, self.state_path)

    def _seed_seen_activities(self) -> None:
        if self.state.get("seen_activity_ids"):
            return
        log_event("debug", {"message": "seed_seen_activities_start"})
        activities = self.strava.recent_activities(days=self.lookback_days)
        log_event("debug", {"message": "seed_seen_activities_done", "count": len(activities)})
        self.state["seen_activity_ids"] = [
            activity["id"] for activity in activities if "id" in activity
        ]
        _save_state(self.state, self.state_path)

    def _notify_new_runs(self, force_chat_id: int | None = None) -> None:
        chat_id = force_chat_id or self.allowed_chat_id
        if not chat_id:
            return

        log_event(
            "debug",
            {"message": "notify_new_runs_start", "chat_id": chat_id, "forced": bool(force_chat_id)},
        )
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
        _save_state(self.state, self.state_path)
        log_event(
            "debug",
            {
                "message": "notify_new_runs_done",
                "activity_count": len(activities),
                "new_run_count": len(new_runs),
            },
        )

        if not new_runs:
            if force_chat_id:
                self._send_message(chat_id, "No new Strava runs since my last check.")
            return

        for run in reversed(new_runs):
            log_event("debug", {"message": "new_run_detail_start", "activity_id": run.get("id")})
            detailed_run = self.strava.detailed_activity(run["id"])
            log_event("debug", {"message": "new_run_detail_done", "activity_id": run.get("id")})
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
                ),
                weekly_plan=weekly_plan_context_for_date(_activity_date(detailed_run)),
                training_goal=training_goal_context(),
                garmin_context=current_garmin_context(),
                conversation=self.conversation,
            )
            log_event("debug", {"message": "new_run_openai_done", "activity_id": run.get("id")})
            self._send_message(chat_id, note)


def _help_text() -> str:
    return (
        "Send me any running question and I will answer using your recent Strava context.\n\n"
        "Commands:\n"
        "/ping - respond with Pong!\n"
        "/recent - summarize recent training\n"
        "/last - send a workout summary for the latest Strava run\n"
        "/run YYYY-MM-DD - send a workout summary for a specific day\n"
        "/suggestplan - suggest a plan idea for next week\n"
        "/plan - show the current weekly plan\n"
        "/setplan <plan> - save this week's plan\n"
        "/goal - show the current overall training goal\n"
        "/setgoal <goal> - save your overall training goal\n"
        "/preferences - show remembered coaching notes\n"
        "/preference <note> - explicitly save a coaching note\n"
        "/check - check Strava for newly synced runs\n"
        "/help - show this help\n\n"
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


def _activity_date(activity: dict[str, Any]):
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return coach_today()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return coach_today()


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any], path: Path) -> None:
    prepare_parent(path)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
