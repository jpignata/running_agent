from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.coach_log import (
    append_run_result,
    append_week_review,
    coach_log_context,
    read_coach_log,
)

METERS_PER_MILE = 1609.344


class CoachLogTest(unittest.TestCase):
    @patch("running_agent.coach_log.planned_workout_for_date", return_value="5 mi easy")
    def test_append_run_result_records_planned_and_completed_run(self, _planned) -> None:
        path = _temp_path()

        entry = append_run_result(
            {
                "id": 123,
                "name": "Morning Run",
                "type": "Run",
                "distance": 5 * METERS_PER_MILE,
                "moving_time": 40 * 60,
                "start_date_local": "2026-05-29T06:00:00Z",
            },
            path=path,
        )

        self.assertEqual(entry["type"], "run_completed")
        self.assertEqual(entry["activity_id"], 123)
        self.assertEqual(entry["run_date"], "2026-05-29")
        self.assertEqual(entry["planned_workout"], "5 mi easy")
        self.assertIn("Morning Run: 5.00 mi", entry["completed_run"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

        entries = read_coach_log(path)
        self.assertEqual(entries[0]["activity_id"], 123)

    @patch("running_agent.coach_log.planned_workout_for_date", return_value=None)
    def test_coach_log_context_formats_recent_entries(self, _planned) -> None:
        path = _temp_path()
        append_run_result(
            {
                "id": 123,
                "name": "Workout",
                "type": "Run",
                "distance": 6 * METERS_PER_MILE,
                "moving_time": 42 * 60,
                "start_date_local": "2026-05-29T06:00:00Z",
            },
            path=path,
        )

        context = coach_log_context(path)

        self.assertIn("Recent coach log:", context)
        self.assertIn("planned: No matching planned workout found.", context)
        self.assertIn("completed: Workout: 6.00 mi", context)

    def test_read_coach_log_skips_blank_lines(self) -> None:
        path = _temp_path()
        path.write_text(json.dumps({"type": "note", "text": "hello"}) + "\n\n", encoding="utf-8")

        self.assertEqual(read_coach_log(path), [{"type": "note", "text": "hello"}])

    def test_append_week_review_records_review_and_context(self) -> None:
        path = _temp_path()

        entry = append_week_review(
            week_start="2026-05-25",
            week_end="2026-05-31",
            summary="Good consistency; keep next week controlled.",
            path=path,
        )

        self.assertEqual(entry["type"], "week_reviewed")
        self.assertEqual(entry["week_start"], "2026-05-25")
        context = coach_log_context(path)
        self.assertIn("week 2026-05-25 to 2026-05-31", context)
        self.assertIn("Good consistency", context)


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
