from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.telegram_agent import TelegramRunningAgent

METERS_PER_MILE = 1609.344


class TelegramGarminContextTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "123"},
        clear=True,
    )
    @patch("running_agent.telegram_agent.TelegramClient", return_value=None)
    @patch("running_agent.telegram_agent.StravaClient", return_value=None)
    @patch("running_agent.telegram_agent.log_event")
    @patch("running_agent.telegram_agent.current_garmin_context", return_value="Garmin context")
    @patch("running_agent.telegram_agent.coaching_reply", return_value="Nice work.")
    def test_last_run_summary_passes_current_garmin_context(
        self,
        coaching_reply,
        _current_garmin_context,
        _log_event,
        _strava_client,
        _telegram_client,
    ) -> None:
        agent = TelegramRunningAgent(state_path=_temp_path())
        agent.strava = _FakeStrava(
            activities=[_run(1, "Easy Run", "2026-05-30T06:00:00Z")],
            latest=_run(1, "Easy Run", "2026-05-30T06:00:00Z"),
            detailed={1: _run(1, "Easy Run", "2026-05-30T06:00:00Z")},
        )
        agent.telegram = _FakeTelegram()

        agent.send_last_run_summary(chat_id=123)

        self.assertEqual(coaching_reply.call_args.kwargs["garmin_context"], "Garmin context")
        self.assertIn("Easy Run: 5.00 mi", agent.telegram.messages[0])

    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "123"},
        clear=True,
    )
    @patch("running_agent.telegram_agent.TelegramClient", return_value=None)
    @patch("running_agent.telegram_agent.StravaClient", return_value=None)
    @patch("running_agent.telegram_agent.append_run_result")
    @patch("running_agent.telegram_agent.log_event")
    @patch("running_agent.telegram_agent.current_garmin_context", return_value="Garmin context")
    @patch("running_agent.telegram_agent.coaching_reply", return_value="Post-run note.")
    def test_new_run_summary_passes_current_garmin_context(
        self,
        coaching_reply,
        _current_garmin_context,
        _log_event,
        _append_run_result,
        _strava_client,
        _telegram_client,
    ) -> None:
        run = _run(2, "Workout", "2026-05-30T06:00:00Z")
        agent = TelegramRunningAgent(state_path=_temp_path())
        agent.state["seen_activity_ids"] = []
        agent.strava = _FakeStrava(activities=[run], latest=run, detailed={2: run})
        agent.telegram = _FakeTelegram()

        agent._notify_new_runs(force_chat_id=123)

        self.assertEqual(coaching_reply.call_args.kwargs["garmin_context"], "Garmin context")
        self.assertIn("New run synced:", agent.telegram.messages[0])


class _FakeStrava:
    def __init__(self, activities: list[dict], latest: dict, detailed: dict[int, dict]):
        self.activities = activities
        self.latest = latest
        self.detailed = detailed

    def recent_activities(self, days: int) -> list[dict]:
        return self.activities

    def latest_run(self, days: int) -> dict:
        return self.latest

    def detailed_activity(self, activity_id: int) -> dict:
        return self.detailed[activity_id]


class _FakeTelegram:
    def __init__(self):
        self.messages: list[str] = []

    def send_message(self, chat_id: int | str, text: str) -> None:
        self.messages.append(text)


def _run(activity_id: int, name: str, start_date_local: str) -> dict:
    return {
        "id": activity_id,
        "type": "Run",
        "name": name,
        "distance": 5 * METERS_PER_MILE,
        "moving_time": 40 * 60,
        "elapsed_time": 40 * 60,
        "start_date_local": start_date_local,
        "laps": [],
    }


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
