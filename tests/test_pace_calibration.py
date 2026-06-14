from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from running_agent.coach_time import COACH_TIME_ZONE
from running_agent.pace_calibration import (
    load_pace_calibration,
    pace_calibration_context,
    save_pace_calibration,
)


class PaceCalibrationTest(unittest.TestCase):
    def test_save_and_load_pace_calibration_trims_text(self) -> None:
        path = _temp_path()

        save_pace_calibration("  VDOT 50, threshold 6:55/mi  ", path)
        loaded = load_pace_calibration(path)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["text"], "VDOT 50, threshold 6:55/mi")
        self.assertIn("updated_at", loaded)

    @patch(
        "running_agent.time_format.coach_now",
        return_value=datetime(2026, 5, 29, 11, 30, tzinfo=COACH_TIME_ZONE),
    )
    def test_pace_calibration_context_humanizes_timestamp(self, _coach_now) -> None:
        path = _pace_file("VDOT 50, easy 8:05-8:45/mi")

        context = pace_calibration_context(path)

        self.assertIn("Current VDOT and pace calibration, last updated 20 minutes ago", context)
        self.assertIn("VDOT 50, easy 8:05-8:45/mi", context)

    def test_empty_pace_calibration_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            save_pace_calibration("   ", _temp_path())


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


def _pace_file(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    path = Path(handle.name)
    with handle:
        json.dump({"updated_at": "2026-05-29T15:10:00+00:00", "text": text}, handle)
    return path


if __name__ == "__main__":
    unittest.main()
