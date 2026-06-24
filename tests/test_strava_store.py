from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.strava_store import (
    format_local_store_health,
    list_run_summaries,
    load_run_detail,
    load_run_summaries,
    local_store_health,
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

    def test_local_store_health_reports_missing_details_races_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summaries_path = root / "activities.json"
            details_dir = root / "details"
            race_results_path = root / "race_results.json"
            save_run_summaries(
                {
                    "1": {
                        "id": 1,
                        "name": "Morning Run",
                        "start_date": "2026-05-01T07:00:00Z",
                    },
                    "2": {
                        "id": 2,
                        "name": "North Jersey 5K",
                        "start_date": "2026-06-01T07:00:00Z",
                    },
                    "3": {
                        "id": 3,
                        "name": "Club Race",
                        "start_date": "2026-06-15T07:00:00Z",
                        "workout_type": 1,
                    },
                    "4": {
                        "id": 4,
                        "name": "Alternating miles",
                        "start_date": "2026-06-20T07:00:00Z",
                    },
                    "5": {
                        "id": 5,
                        "name": "Warmup",
                        "start_date": "2026-06-01T06:00:00Z",
                    },
                },
                summaries_path,
            )
            save_run_detail({"id": 2, "name": "North Jersey 5K"}, details_dir)
            race_results_path.write_text(
                (
                    '{"results": ['
                    '{"race_date": "2026-06-01", "race_name": "North Jersey 5K", '
                    '"distance": "5K", "time": "19:44"}'
                    "]} "
                ),
                encoding="utf-8",
            )

            report = local_store_health(summaries_path, details_dir, race_results_path)

            self.assertIsNotNone(report["last_sync"])
            self.assertEqual(report["activity_count"], 5)
            self.assertEqual(report["detail_count"], 1)
            self.assertEqual(report["missing_detail_count"], 4)
            self.assertEqual([item["id"] for item in report["missing_details"]], [4, 3, 5, 1])
            self.assertEqual([item["id"] for item in report["latest_race_like"]], [3, 2])
            self.assertEqual(report["race_results"][0]["race_name"], "North Jersey 5K")
            self.assertIn("fetch missing details", report["repair_action"])

            formatted = format_local_store_health(report)
            self.assertIn("Local Strava store health", formatted)
            self.assertIn("Activities: 5", formatted)
            self.assertIn("Missing detail activity IDs: 4, 3, 5, 1", formatted)
            self.assertIn("id 3: 2026-06-15, Club Race", formatted)
            self.assertIn("2026-06-01: North Jersey 5K, 5K in 19:44", formatted)

    def test_local_store_health_recommends_sync_when_store_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            report = local_store_health(
                root / "missing_activities.json",
                root / "missing_details",
                root / "missing_race_results.json",
            )

            self.assertIsNone(report["last_sync"])
            self.assertEqual(report["activity_count"], 0)
            self.assertEqual(report["detail_count"], 0)
            self.assertEqual(report["missing_detail_count"], 0)
            self.assertIn("build the local store", report["repair_action"])
            self.assertIn("Last sync: never", format_local_store_health(report))


if __name__ == "__main__":
    unittest.main()
