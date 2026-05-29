from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from running_agent.goal_store import (
    load_training_goal,
    save_training_goal,
    training_goal_context,
)


class GoalStoreTest(unittest.TestCase):
    def test_save_and_load_training_goal_trims_text(self) -> None:
        path = _temp_path()

        save_training_goal("  NYC Marathon, sub-3:10  ", path)
        loaded = load_training_goal(path)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["text"], "NYC Marathon, sub-3:10")
        self.assertIn("updated_at", loaded)

    def test_training_goal_context_humanizes_timestamp(self) -> None:
        path = _goal_file("NYC Marathon, sub-3:10")

        context = training_goal_context(path)

        self.assertIn("Overall training goal, last updated Friday, May 29", context)
        self.assertIn("NYC Marathon, sub-3:10", context)
        self.assertNotIn("2026-05-29T15:10:00", context)

    def test_empty_goal_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            save_training_goal("   ", _temp_path())


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


def _goal_file(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    path = Path(handle.name)
    with handle:
        json.dump({"updated_at": "2026-05-29T15:10:00+00:00", "text": text}, handle)
    return path


if __name__ == "__main__":
    unittest.main()
