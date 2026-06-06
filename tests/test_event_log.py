from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from running_agent.event_log import DEBUG_STDOUT_ENV, QUIET_STDOUT_ENV, log_event


class EventLogTest(unittest.TestCase):
    def test_log_event_prints_timestamped_line(self) -> None:
        with patch("builtins.print") as print_mock:
            log_event("rx", {"chat_id": 123, "text": "hello\nthere"})

        printed_line = print_mock.call_args.args[0]
        self.assertIn(' rx chat_id=123 text="hello\\nthere"', printed_line)
        self.assertEqual(print_mock.call_args.kwargs, {"flush": True})

    def test_log_event_quotes_and_escapes_text_field(self) -> None:
        with patch("builtins.print") as print_mock:
            log_event("tx", {"chat_id": 123, "text": 'he said "go"'})

        self.assertIn(' tx chat_id=123 text="he said \\"go\\""', print_mock.call_args.args[0])

    def test_debug_event_does_not_print_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("builtins.print") as print_mock:
            log_event("debug", {"message": "work_start"})

        print_mock.assert_not_called()

    def test_debug_event_prints_when_enabled(self) -> None:
        with patch.dict(os.environ, {DEBUG_STDOUT_ENV: "1"}), patch("builtins.print") as print_mock:
            log_event("debug", {"message": "work_start"})

        self.assertIn(" debug message=work_start", print_mock.call_args.args[0])

    def test_quiet_event_log_suppresses_stdout(self) -> None:
        with patch.dict(os.environ, {QUIET_STDOUT_ENV: "1"}), patch("builtins.print") as print_mock:
            log_event("rx", {"chat_id": 123, "text": "hello"})

        print_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
