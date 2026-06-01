from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from urllib.error import URLError

from .agent_state import load_agent_state, save_agent_state
from .auth import load_env_file, require_env
from .coach_agent import DEFAULT_LOOKBACK_DAYS, CoachAgent
from .event_log import log_event
from .storage_paths import STATE_PATH
from .strava_client import StravaClient
from .telegram_client import TelegramClient

TRANSIENT_ERRORS = (
    TimeoutError,
    socket.timeout,
    ConnectionError,
    URLError,
)


class TelegramTransport:
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
        self.state = load_agent_state(state_path)
        self.telegram = telegram_client or TelegramClient(require_env("TELEGRAM_BOT_TOKEN"))
        self._strava = strava_client or StravaClient()
        self.allowed_chat_id = (
            allowed_chat_id
            or os.environ.get("TELEGRAM_CHAT_ID")
            or self.state.get("telegram_chat_id")
        )
        self.coach = CoachAgent(
            lookback_days=lookback_days,
            strava_client=self._strava,
            state=self.state,
            save_state=self._save_state,
        )

    @property
    def strava(self) -> StravaClient:
        return self.coach.strava

    @strava.setter
    def strava(self, value: StravaClient) -> None:
        self._strava = value
        self.coach.strava = value

    @property
    def conversation(self) -> list[dict[str, str]]:
        return self.coach.conversation

    def run_forever(self) -> None:
        self._seed_seen_activities()
        print("Running Telegram coach. Press Ctrl+C to stop.")
        next_strava_check = time.monotonic() + self.poll_seconds

        while True:
            try:
                self._handle_telegram_updates()
                self._deliver_scheduled_messages(run_new_check=False)
                if time.monotonic() >= next_strava_check:
                    self._deliver_messages(self.coach.check_new_runs(force=False))
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
            self._deliver_messages(self.coach.handle_message(text), chat_id=chat_id)
        self._save_state()

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

    def _send_message(self, chat_id: int | str, text: str) -> None:
        log_event(
            "debug", {"message": "telegram_send_start", "chat_id": chat_id, "chars": len(text)}
        )
        self.telegram.send_message(chat_id, text)
        log_event("tx", {"chat_id": chat_id, "text": text})
        log_event(
            "debug", {"message": "telegram_send_done", "chat_id": chat_id, "chars": len(text)}
        )

    def _deliver_messages(
        self,
        messages: list[str],
        chat_id: int | str | None = None,
    ) -> None:
        target_chat_id = chat_id or self.allowed_chat_id
        if not target_chat_id:
            return
        for message in messages:
            self._send_message(target_chat_id, message)

    def _deliver_scheduled_messages(self, run_new_check: bool = True) -> None:
        if not self.allowed_chat_id:
            return
        if run_new_check:
            messages = self.coach.tick()
        else:
            self.coach.refresh_garmin_cache_if_due()
            messages = []
            daily = self.coach.daily_checkin_if_due()
            if daily:
                messages.append(daily)
            sunday = self.coach.sunday_plan_if_due()
            if sunday:
                messages.append(sunday)
        self._deliver_messages(messages)

    def _save_state(self) -> None:
        save_agent_state(self.state, self.state_path)

    # Compatibility wrappers while callers/tests move to CoachAgent.
    def _handle_message(self, chat_id: int, text: str) -> None:
        self._deliver_messages(self.coach.handle_message(text), chat_id=chat_id)

    def _coach_reply(self, text: str) -> str:
        return self.coach.coach_reply(text)

    def _training_summary(self) -> str:
        return self.coach.training_summary()

    def send_last_run_summary(self, chat_id: int | str | None = None) -> None:
        self._deliver_messages([self.coach.last_run_summary()], chat_id=chat_id)

    def send_run_summary_for_date(
        self,
        date_text: str,
        chat_id: int | str | None = None,
        search_days: int = 120,
    ) -> None:
        self._deliver_messages(
            [self.coach.run_summary_for_date(date_text, search_days=search_days)],
            chat_id=chat_id,
        )

    def send_next_week_plan(self, chat_id: int | str | None = None) -> None:
        self._deliver_messages([self.coach.next_week_plan()], chat_id=chat_id)

    def _send_sunday_plan_if_due(self) -> None:
        if not self.allowed_chat_id:
            return
        message = self.coach.sunday_plan_if_due()
        if message:
            self._send_message(self.allowed_chat_id, message)

    def _send_daily_checkin_if_due(self) -> None:
        if not self.allowed_chat_id:
            return
        message = self.coach.daily_checkin_if_due()
        if message:
            self._send_message(self.allowed_chat_id, message)

    def _refresh_garmin_cache_if_due(self) -> None:
        self.coach.refresh_garmin_cache_if_due()

    def _seed_seen_activities(self) -> None:
        self.coach.seed_seen_activities()

    def _notify_new_runs(self, force_chat_id: int | None = None) -> None:
        self._deliver_messages(
            self.coach.check_new_runs(force=force_chat_id is not None),
            chat_id=force_chat_id,
        )
