from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.telegram_transport import TelegramTransport


class TelegramRetryTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "123"},
        clear=True,
    )
    @patch("running_agent.telegram_transport.TelegramClient", return_value=None)
    @patch("running_agent.telegram_transport.StravaClient", return_value=None)
    @patch("running_agent.telegram_transport.time.sleep")
    @patch("running_agent.telegram_transport.log_event")
    @patch("builtins.print")
    def test_run_forever_retries_transient_timeout(
        self,
        _print,
        log_event,
        sleep,
        _strava_client,
        _telegram_client,
    ) -> None:
        agent = _RetryProbeAgent(state_path=_temp_path())

        with self.assertRaises(KeyboardInterrupt):
            agent.run_forever()

        self.assertEqual(agent.update_calls, 2)
        sleep.assert_called_once_with(5)
        log_event.assert_any_call(
            "debug",
            {"message": "transient_loop_error", "error": "TimeoutError('timed out')"},
        )


class _RetryProbeAgent(TelegramTransport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_calls = 0

    def _seed_seen_activities(self) -> None:
        return None

    def _handle_telegram_updates(self) -> None:
        self.update_calls += 1
        if self.update_calls == 1:
            raise TimeoutError("timed out")
        raise KeyboardInterrupt


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
