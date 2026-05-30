from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from running_agent.telegram_client import SEND_MESSAGE_TIMEOUT_SECONDS, TelegramClient


class TelegramClientTest(unittest.TestCase):
    @patch("running_agent.telegram_client.urlopen")
    def test_get_updates_uses_long_poll_timeout_plus_buffer(self, urlopen) -> None:
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"ok": True, "result": []}
        ).encode("utf-8")

        TelegramClient("token").get_updates(offset=123, timeout=25)

        self.assertEqual(urlopen.call_args.kwargs["timeout"], 35)

    @patch("running_agent.telegram_client.urlopen")
    def test_send_message_uses_short_send_timeout(self, urlopen) -> None:
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"ok": True, "result": {}}
        ).encode("utf-8")

        TelegramClient("token").send_message(123, "hello")

        self.assertEqual(urlopen.call_args.kwargs["timeout"], SEND_MESSAGE_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
