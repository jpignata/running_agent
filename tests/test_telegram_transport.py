from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from running_agent.telegram_transport import TelegramTransport


class TelegramTransportTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "123"},
        clear=True,
    )
    @patch("running_agent.telegram_transport.log_event")
    @patch("running_agent.telegram_transport.StravaClient")
    def test_message_updates_are_delivered_from_coach(
        self,
        strava_client,
        _log_event,
    ) -> None:
        strava_client.return_value = _FakeStrava()
        telegram = _FakeTelegram(
            updates=[
                {
                    "update_id": 10,
                    "message": {"text": "/ping", "chat": {"id": 123}},
                }
            ]
        )
        transport = TelegramTransport(
            state_path=_temp_path(),
            telegram_client=telegram,
        )

        transport._handle_telegram_updates()

        self.assertEqual(telegram.messages, [(123, "Pong!")])
        self.assertEqual(transport.state["telegram_update_offset"], 11)

    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "123"},
        clear=True,
    )
    @patch("running_agent.telegram_transport.log_event")
    @patch("running_agent.telegram_transport.StravaClient")
    def test_scheduled_messages_are_delivered_from_tick(self, strava_client, _log_event) -> None:
        strava_client.return_value = _FakeStrava()
        telegram = _FakeTelegram()
        transport = TelegramTransport(state_path=_temp_path(), telegram_client=telegram)
        transport.coach.tick = Mock(return_value=["Scheduled note"])

        transport._deliver_scheduled_messages()

        self.assertEqual(telegram.messages, [("123", "Scheduled note")])
        transport.coach.tick.assert_called_once_with()

    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "123"},
        clear=True,
    )
    @patch("running_agent.telegram_transport.log_event")
    @patch("running_agent.telegram_transport.StravaClient")
    def test_forced_new_run_check_delivers_agent_messages(self, strava_client, _log_event) -> None:
        strava_client.return_value = _FakeStrava()
        telegram = _FakeTelegram()
        transport = TelegramTransport(state_path=_temp_path(), telegram_client=telegram)
        transport.coach.check_new_runs = Mock(return_value=["Run note"])

        transport._notify_new_runs(force_chat_id=123)

        self.assertEqual(telegram.messages, [(123, "Run note")])
        transport.coach.check_new_runs.assert_called_once_with(force=True)


class _FakeTelegram:
    def __init__(self, updates: list[dict] | None = None):
        self.updates = updates or []
        self.messages: list[tuple[int | str, str]] = []

    def get_updates(self, offset=None, timeout=25) -> list[dict]:
        return self.updates

    def send_message(self, chat_id: int | str, text: str) -> None:
        self.messages.append((chat_id, text))


class _FakeStrava:
    def recent_activities(self, days: int) -> list[dict]:
        return []


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
