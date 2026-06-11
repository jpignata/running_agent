from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from running_agent.race_results import (
    format_race_time,
    official_result_for_activity,
    parse_race_distance,
    parse_race_time,
    race_results_context,
    save_race_result,
)


class RaceResultsTest(unittest.TestCase):
    def test_save_race_result_normalizes_distance_and_time(self) -> None:
        path = _temp_path()

        result = save_race_result(
            race_name="North Jersey Pride Run",
            race_date="2026-06-07",
            distance="5k",
            time="19:59",
            path=path,
        )

        self.assertEqual(result["distance"], "5K")
        self.assertEqual(result["distance_meters"], 5000.0)
        self.assertEqual(result["time"], "19:59")
        self.assertEqual(result["time_seconds"], 1199)

    def test_race_results_context_lists_saved_results(self) -> None:
        path = _results_file()

        context = race_results_context(path)

        self.assertIn("Official race results saved by the athlete", context)
        self.assertIn("North Jersey Pride Run, 5K in 19:59", context)

    @patch("running_agent.race_results.load_race_results")
    def test_official_result_for_activity_matches_same_date(self, load_race_results) -> None:
        load_race_results.return_value = [
            {
                "race_name": "North Jersey Pride Run",
                "race_date": "2026-06-07",
                "distance": "5K",
                "distance_meters": 5000.0,
                "time": "19:59",
                "time_seconds": 1199,
            }
        ]

        result = official_result_for_activity(
            {
                "name": "Morning Run",
                "start_date_local": "2026-06-07T08:00:00Z",
            }
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["time_seconds"], 1199)

    def test_parse_helpers(self) -> None:
        self.assertEqual(parse_race_distance("10K"), ("10K", 10000.0))
        self.assertEqual(parse_race_time("1:02:03"), 3723)
        self.assertEqual(format_race_time(3723), "1:02:03")


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


def _results_file() -> Path:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    path = Path(handle.name)
    with handle:
        json.dump(
            {
                "results": [
                    {
                        "race_name": "North Jersey Pride Run",
                        "race_date": "2026-06-07",
                        "distance": "5K",
                        "time": "19:59",
                        "source": "athlete",
                        "updated_at": "2026-06-11T15:00:00+00:00",
                    }
                ]
            },
            handle,
        )
    return path


if __name__ == "__main__":
    unittest.main()
