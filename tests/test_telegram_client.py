from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from running_agent.telegram_client import (
    GET_UPDATES_HTTP_BUFFER_SECONDS,
    GET_UPDATES_TIMEOUT_SECONDS,
    SEND_MESSAGE_TIMEOUT_SECONDS,
    TelegramClient,
)


class TelegramClientTest(unittest.TestCase):
    @patch("running_agent.telegram_client.urlopen")
    def test_get_updates_uses_long_poll_timeout_plus_buffer(self, urlopen) -> None:
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"ok": True, "result": []}
        ).encode("utf-8")

        TelegramClient("token").get_updates(offset=123)

        self.assertEqual(
            urlopen.call_args.kwargs["timeout"],
            GET_UPDATES_TIMEOUT_SECONDS + GET_UPDATES_HTTP_BUFFER_SECONDS,
        )

    @patch("running_agent.telegram_client.urlopen")
    def test_get_updates_honors_explicit_poll_timeout(self, urlopen) -> None:
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"ok": True, "result": []}
        ).encode("utf-8")

        TelegramClient("token").get_updates(offset=123, timeout=25)

        self.assertEqual(urlopen.call_args.kwargs["timeout"], 25 + GET_UPDATES_HTTP_BUFFER_SECONDS)

    @patch("running_agent.telegram_client.urlopen")
    def test_send_message_uses_short_send_timeout(self, urlopen) -> None:
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"ok": True, "result": {}}
        ).encode("utf-8")

        TelegramClient("token").send_message(123, "hello")

        self.assertEqual(urlopen.call_args.kwargs["timeout"], SEND_MESSAGE_TIMEOUT_SECONDS)

    @patch("running_agent.telegram_client.urlopen")
    def test_get_file_returns_telegram_file_result(self, urlopen) -> None:
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"ok": True, "result": {"file_path": "photos/file.jpg"}}
        ).encode("utf-8")

        result = TelegramClient("token").get_file("file-id")

        self.assertEqual(result, {"file_path": "photos/file.jpg"})
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload, {"file_id": "file-id"})

    @patch("running_agent.telegram_client.urlopen")
    def test_download_file_reads_from_file_api(self, urlopen) -> None:
        urlopen.return_value.__enter__.return_value.read.return_value = b"image-bytes"

        body = TelegramClient("token").download_file("photos/file.jpg")

        self.assertEqual(body, b"image-bytes")
        self.assertEqual(
            urlopen.call_args.args[0].full_url,
            "https://api.telegram.org/file/bottoken/photos/file.jpg",
        )


if __name__ == "__main__":
    unittest.main()
