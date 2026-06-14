from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from running_agent.event_log import (
    DEBUG_STDOUT_ENV,
    QUIET_STDOUT_ENV,
    TRACE_STDOUT_ENV,
    log_event,
    start_trace,
)


class EventLogTest(unittest.TestCase):
    def test_log_event_prints_compact_line(self) -> None:
        with patch("builtins.print") as print_mock:
            log_event("rx", {"chat_id": 123, "text": "hello\nthere"})

        printed_line = print_mock.call_args.args[0]
        self.assertEqual(printed_line, 'rx chat_id=123 text="hello\\nthere"')
        self.assertEqual(print_mock.call_args.kwargs, {"flush": True})

    def test_log_event_quotes_and_escapes_text_field(self) -> None:
        with patch("builtins.print") as print_mock:
            log_event("tx", {"chat_id": 123, "text": 'he said "go"'})

        self.assertEqual(
            'tx chat_id=123 text="he said \\"go\\""',
            print_mock.call_args.args[0],
        )

    def test_debug_event_does_not_print_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("builtins.print") as print_mock:
            log_event("debug", {"message": "work_start"})

        print_mock.assert_not_called()

    def test_debug_event_prints_when_enabled(self) -> None:
        with patch.dict(os.environ, {DEBUG_STDOUT_ENV: "1"}), patch("builtins.print") as print_mock:
            log_event("debug", {"message": "work_start"})

        self.assertEqual("debug message=work_start", print_mock.call_args.args[0])

    def test_quiet_event_log_suppresses_stdout(self) -> None:
        with patch.dict(os.environ, {QUIET_STDOUT_ENV: "1"}), patch("builtins.print") as print_mock:
            log_event("rx", {"chat_id": 123, "text": "hello"})

        print_mock.assert_not_called()

    def test_trace_events_print_only_when_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("builtins.print") as print_mock:
            trace = start_trace(source="repl", interaction="message", command="/ping")
            trace.close(reply_count=1)

        print_mock.assert_not_called()

        with (
            patch.dict(os.environ, {TRACE_STDOUT_ENV: "1"}, clear=True),
            patch("builtins.print") as print_mock,
        ):
            trace = start_trace(source="repl", interaction="message", command="/ping")
            trace.close(reply_count=1)

        lines = [call.args[0] for call in print_mock.call_args_list]
        self.assertTrue(any(line.startswith("trace_start ") for line in lines))
        self.assertTrue(any(line.startswith("trace_end ") for line in lines))
        self.assertTrue(any("source=repl" in line for line in lines))
        self.assertTrue(any("interaction=message" in line for line in lines))
        self.assertTrue(any("reply_count=1" in line for line in lines))

    def test_active_trace_id_is_added_to_nested_events(self) -> None:
        with (
            patch.dict(
                os.environ,
                {TRACE_STDOUT_ENV: "1", DEBUG_STDOUT_ENV: "1"},
                clear=True,
            ),
            patch("builtins.print") as print_mock,
        ):
            trace = start_trace(source="repl", interaction="message")
            log_event("debug", {"message": "inside"})
            trace.close()

        debug_line = next(
            call.args[0] for call in print_mock.call_args_list if call.args[0].startswith("debug ")
        )
        self.assertIn(f"trace_id={trace.trace_id}", debug_line)


if __name__ == "__main__":
    unittest.main()
