from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 3900
GET_UPDATES_TIMEOUT_SECONDS = 5
GET_UPDATES_HTTP_BUFFER_SECONDS = 5
SEND_MESSAGE_TIMEOUT_SECONDS = 5


class TelegramClient:
    def __init__(self, bot_token: str):
        self.base_url = f"{TELEGRAM_API_BASE}/bot{bot_token}"
        self.file_base_url = f"{TELEGRAM_API_BASE}/file/bot{bot_token}"

    def get_updates(
        self,
        offset: int | None = None,
        timeout: int = GET_UPDATES_TIMEOUT_SECONDS,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self._post(
            "getUpdates",
            payload,
            timeout_seconds=timeout + GET_UPDATES_HTTP_BUFFER_SECONDS,
        ).get("result", [])

    def send_message(self, chat_id: int | str, text: str) -> None:
        for chunk in _message_chunks(text):
            self._post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
                timeout_seconds=SEND_MESSAGE_TIMEOUT_SECONDS,
            )

    def get_file(self, file_id: str) -> dict[str, Any]:
        return self._post(
            "getFile",
            {"file_id": file_id},
            timeout_seconds=SEND_MESSAGE_TIMEOUT_SECONDS,
        ).get("result", {})

    def download_file(self, file_path: str) -> bytes:
        request = Request(f"{self.file_base_url}/{file_path}", method="GET")
        try:
            with urlopen(request, timeout=SEND_MESSAGE_TIMEOUT_SECONDS) as response:
                return response.read()
        except HTTPError as error:
            body = error.read().decode("utf-8")
            raise RuntimeError(
                f"Telegram file download failed with HTTP {error.code}: {body}"
            ) from error

    def _post(
        self,
        method: str,
        payload: dict[str, Any],
        timeout_seconds: int = SEND_MESSAGE_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8")
            raise RuntimeError(f"Telegram request failed with HTTP {error.code}: {body}") from error

        if not body.get("ok"):
            raise RuntimeError(f"Telegram request failed: {body}")
        return body


def _message_chunks(text: str) -> list[str]:
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:MAX_MESSAGE_LENGTH])
        remaining = remaining[MAX_MESSAGE_LENGTH:]
    return chunks
