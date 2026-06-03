from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.strava_store import (
    list_run_summaries,
    load_run_detail,
    load_run_summaries,
    run_detail_exists,
    save_run_detail,
    save_run_summaries,
)


class StravaStoreTest(unittest.TestCase):
    def test_save_and_list_run_summaries_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "activities.json"

            save_run_summaries(
                {
                    "1": {"id": 1, "start_date": "2026-05-01T07:00:00Z"},
                    "2": {"id": 2, "start_date": "2026-06-01T07:00:00Z"},
                },
                path,
            )

            self.assertEqual(set(load_run_summaries(path)), {"1", "2"})
            self.assertEqual([run["id"] for run in list_run_summaries(path)], [2, 1])

    def test_save_and_load_run_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            details_dir = Path(tmp) / "details"

            save_run_detail({"id": 123, "name": "Track"}, details_dir)

            self.assertTrue(run_detail_exists(123, details_dir))
            self.assertEqual(load_run_detail(123, details_dir), {"id": 123, "name": "Track"})


if __name__ == "__main__":
    unittest.main()
