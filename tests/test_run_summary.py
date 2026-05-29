from __future__ import annotations

import unittest

from running_agent.run_summary import _fallback_summary

METERS_PER_MILE = 1609.344


class RunSummaryTest(unittest.TestCase):
    def test_fallback_summary_includes_error_and_activity_context(self) -> None:
        summary = _fallback_summary(
            {
                "name": "Morning Run",
                "distance": 5 * METERS_PER_MILE,
                "moving_time": 40 * 60,
                "elapsed_time": 42 * 60,
                "start_date_local": "2026-05-29T05:45:00Z",
                "laps": [],
            },
            RuntimeError("model unavailable"),
        )

        self.assertIn("AI coaching was unavailable (model unavailable).", summary)
        self.assertIn("Morning Run: 5.00 mi", summary)
        self.assertIn("No lap-by-lap data", summary)
        self.assertIn("Basic read:", summary)


if __name__ == "__main__":
    unittest.main()
