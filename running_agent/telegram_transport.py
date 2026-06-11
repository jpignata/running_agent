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
                self._deliver_messages(self.coach.tick())
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
            caption = (message.get("caption") or "").strip()
            photo = message.get("photo") or []
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None or (not text and not photo):
                continue
            if not self._chat_allowed(chat_id):
                continue
            if photo:
                log_event("rx", {"chat_id": chat_id, "text": caption, "photo": True})
                self._deliver_messages(
                    [self._image_reply_from_message(photo, caption)],
                    chat_id=chat_id,
                )
            else:
                log_event("rx", {"chat_id": chat_id, "text": text})
                self._deliver_messages(
                    self.coach.handle_message(text, source="telegram"),
                    chat_id=chat_id,
                )
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

    def _deliver_scheduled_messages(self) -> None:
        if not self.allowed_chat_id:
            return
        self._deliver_messages(self.coach.tick(source="telegram_scheduler"))

    def _save_state(self) -> None:
        save_agent_state(self.state, self.state_path)

    def _seed_seen_activities(self) -> None:
        self.coach.seed_seen_activities()

    def _notify_new_runs(self, force_chat_id: int | None = None) -> None:
        self._deliver_messages(
            self.coach.check_new_runs(force=force_chat_id is not None),
            chat_id=force_chat_id,
        )

    def _image_reply_from_message(self, photo_sizes: list[dict], caption: str) -> str:
        try:
            photo = _largest_photo(photo_sizes)
            file_id = photo.get("file_id")
            if not file_id:
                return "I received the image, but Telegram did not include a downloadable file ID."
            file_info = self.telegram.get_file(file_id)
            file_path = file_info.get("file_path")
            if not file_path:
                return "I received the image, but Telegram did not return a file path for it."
            image_bytes = self.telegram.download_file(file_path)
            return self.coach.coach_image_reply(
                caption=caption,
                image_bytes=image_bytes,
                mime_type=_mime_type_for_file_path(file_path),
            )
        except RuntimeError as error:
            return f"Something failed while reading that image: {error}"


def _largest_photo(photo_sizes: list[dict]) -> dict:
    return max(
        photo_sizes,
        key=lambda item: (
            int(item.get("file_size") or 0),
            int(item.get("width") or 0) * int(item.get("height") or 0),
        ),
    )


def _mime_type_for_file_path(file_path: str) -> str:
    lower = file_path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"
