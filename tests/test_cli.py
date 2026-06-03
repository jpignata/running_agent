from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from running_agent import cli


class CliTest(unittest.TestCase):
    @patch("builtins.print")
    @patch("running_agent.cli.StravaClient")
    @patch(
        "running_agent.cli.sync_strava_runs",
        return_value={"runs_seen": 2, "summaries_saved": 2, "details_fetched": 1},
    )
    @patch("sys.argv", ["running-agent", "sync-strava", "--days", "90"])
    def test_sync_strava_command_backfills_local_store(
        self,
        sync_strava_runs,
        strava_client,
        print_,
    ) -> None:
        client = Mock()
        strava_client.return_value = client

        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        sync_strava_runs.assert_called_once_with(client, days=90)
        print_.assert_called_once_with(
            "Synced 2 Strava runs; saved 2 summaries; fetched 1 detailed activities."
        )


if __name__ == "__main__":
    unittest.main()
