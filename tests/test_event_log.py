from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.event_log import DEBUG_STDOUT_ENV, log_event, read_event_log


class EventLogTest(unittest.TestCase):
    def test_log_event_appends_timestamped_jsonl_entry(self) -> None:
        path = _temp_path()

        with patch("builtins.print") as print_mock:
            log_event("rx", {"chat_id": 123, "text": "hello\nthere"}, path=path)

        entries = read_event_log(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "rx")
        self.assertEqual(entries[0]["chat_id"], 123)
        self.assertEqual(entries[0]["text"], "hello\nthere")
        self.assertIn("timestamp", entries[0])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        printed_line = print_mock.call_args.args[0]
        self.assertIn(" rx chat_id=123 text=hello\\nthere", printed_line)
        self.assertEqual(print_mock.call_args.kwargs, {"flush": True})

    def test_read_event_log_returns_empty_for_missing_file(self) -> None:
        self.assertEqual(read_event_log(Path("/tmp/running-agent-missing-events.jsonl")), [])

    def test_debug_event_does_not_print_by_default(self) -> None:
        path = _temp_path()

        with patch.dict(os.environ, {}, clear=True), patch("builtins.print") as print_mock:
            log_event("debug", {"message": "work_start"}, path=path)

        self.assertEqual(read_event_log(path)[0]["type"], "debug")
        print_mock.assert_not_called()

    def test_debug_event_prints_when_enabled(self) -> None:
        path = _temp_path()

        with patch.dict(os.environ, {DEBUG_STDOUT_ENV: "1"}), patch("builtins.print") as print_mock:
            log_event("debug", {"message": "work_start"}, path=path)

        self.assertIn(" debug message=work_start", print_mock.call_args.args[0])


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
