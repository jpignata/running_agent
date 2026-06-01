from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from running_agent.garmin_cache import (
    cached_garmin_snapshots,
    load_garmin_snapshots,
    refresh_garmin_snapshots,
)


class GarminCacheTest(unittest.TestCase):
    def test_refresh_garmin_snapshots_writes_recent_dates_in_order(self) -> None:
        path = _temp_path()
        client = _FakeGarminClient()

        refresh_garmin_snapshots(
            client=client,
            end_date=date(2026, 6, 1),
            days=3,
            path=path,
        )

        self.assertEqual(
            [call[0].isoformat() for call in client.calls],
            ["2026-05-30", "2026-05-31", "2026-06-01"],
        )
        self.assertTrue(all(call[1] == 0 for call in client.calls))
        self.assertEqual(
            [snapshot["date"] for snapshot in cached_garmin_snapshots(date(2026, 6, 1), 3, path)],
            ["2026-05-30", "2026-05-31", "2026-06-01"],
        )

    def test_refresh_garmin_snapshots_prunes_old_dates(self) -> None:
        path = _temp_path()
        path.write_text(
            '{"2026-01-01": {"date": "2026-01-01"}, "2026-05-31": {"date": "2026-05-31"}}'
        )

        refresh_garmin_snapshots(
            client=_FakeGarminClient(),
            end_date=date(2026, 6, 1),
            days=1,
            path=path,
            retention_days=2,
        )

        snapshots = load_garmin_snapshots(path)
        self.assertNotIn("2026-01-01", snapshots)
        self.assertIn("2026-05-31", snapshots)
        self.assertIn("2026-06-01", snapshots)


class _FakeGarminClient:
    def __init__(self) -> None:
        self.calls: list[tuple[date, int]] = []

    def readiness_snapshot(self, target_date: date, vo2max_lookback_days: int = 30) -> dict:
        self.calls.append((target_date, vo2max_lookback_days))
        return {"date": target_date.isoformat()}


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
