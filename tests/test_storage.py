from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from running_agent.storage import (
    append_jsonl,
    read_json_file,
    read_jsonl,
    write_json_file,
    write_text_file,
)


class StorageTest(unittest.TestCase):
    def test_write_json_file_creates_private_parent_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "state.json"

            write_json_file(path, {"b": 2, "a": 1})

            self.assertEqual(read_json_file(path), {"a": 1, "b": 2})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_write_text_file_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "note.txt"
            write_text_file(path, "old")

            write_text_file(path, "new")

            self.assertEqual(path.read_text(encoding="utf-8"), "new")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_read_json_file_can_suppress_decode_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text("{", encoding="utf-8")

            self.assertEqual(read_json_file(path, default={}, suppress_errors=True), {})
            with self.assertRaises(json.JSONDecodeError):
                read_json_file(path)

    def test_jsonl_helpers_skip_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "coach_log.jsonl"

            append_jsonl(path, {"type": "note", "text": "first"})
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            append_jsonl(path, {"type": "note", "text": "second"})

            self.assertEqual(
                read_jsonl(path),
                [
                    {"type": "note", "text": "first"},
                    {"type": "note", "text": "second"},
                ],
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
