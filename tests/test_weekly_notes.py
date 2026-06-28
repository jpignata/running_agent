from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from running_agent.weekly_notes import (
    append_weekly_note,
    weekly_notes_context,
    weekly_notes_for_week,
)


class WeeklyNotesTest(unittest.TestCase):
    @patch("running_agent.weekly_notes.coach_today", return_value=date(2026, 6, 27))
    def test_append_weekly_note_trims_and_defaults_to_current_coach_week(
        self, _coach_today
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "weekly_notes.jsonl"

            entry = append_weekly_note("  moved long run to Sunday  ", path=path)

            self.assertEqual(entry["week_start"], "2026-06-22")
            self.assertEqual(entry["note"], "moved long run to Sunday")
            self.assertEqual(
                weekly_notes_for_week(date(2026, 6, 22), path=path),
                [entry],
            )

    def test_append_weekly_note_rejects_empty_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "weekly_notes.jsonl"

            with self.assertRaisesRegex(RuntimeError, "cannot be empty"):
                append_weekly_note("   ", path=path)

    def test_weekly_notes_context_filters_by_week_and_limits_to_recent_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "weekly_notes.jsonl"
            append_weekly_note("older reviewed-week note", week_start=date(2026, 6, 22), path=path)
            append_weekly_note("target reviewed-week note", week_start=date(2026, 6, 22), path=path)
            append_weekly_note("other week note", week_start=date(2026, 6, 29), path=path)

            context = weekly_notes_context(date(2026, 6, 22), path=path, limit=1)

            self.assertIn("Athlete notes for reviewed week:", context)
            self.assertNotIn("older reviewed-week note", context)
            self.assertIn("target reviewed-week note", context)
            self.assertNotIn("other week note", context)

    def test_weekly_notes_context_handles_empty_week(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "weekly_notes.jsonl"

            context = weekly_notes_context(date(2026, 6, 22), path=path)

            self.assertEqual(context, "No athlete notes were saved for the reviewed week.")


if __name__ == "__main__":
    unittest.main()
