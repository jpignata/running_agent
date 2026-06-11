from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.coaching_guidance import coaching_philosophy_context


class CoachingGuidanceTest(unittest.TestCase):
    def test_coaching_philosophy_context_reads_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as handle:
            handle.write("Coaching philosophy:\n- Keep easy days easy.")
            handle.flush()

            context = coaching_philosophy_context(Path(handle.name))

        self.assertEqual(context, "Coaching philosophy:\n- Keep easy days easy.")

    def test_coaching_philosophy_context_handles_missing_file(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "missing-running-agent-philosophy.txt"
        if missing_path.exists():
            missing_path.unlink()

        context = coaching_philosophy_context(missing_path)

        self.assertEqual(context, "No coaching philosophy has been provided.")


if __name__ == "__main__":
    unittest.main()
