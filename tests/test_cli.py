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

    @patch("builtins.print")
    @patch("running_agent.cli.StravaClient")
    @patch("running_agent.cli.generate_coach_reflection", return_value="Updated thesis")
    @patch("sys.argv", ["running-agent", "reflect", "--days", "30"])
    def test_reflect_command_regenerates_coach_reflection(
        self,
        generate_coach_reflection,
        strava_client,
        print_,
    ) -> None:
        client = Mock()
        strava_client.return_value = client

        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        generate_coach_reflection.assert_called_once_with(client, lookback_days=30)
        print_.assert_called_once_with("Updated thesis")

    @patch("builtins.print")
    @patch("running_agent.cli.StravaClient")
    @patch("running_agent.cli.CoachAgent")
    @patch("sys.argv", ["running-agent", "debug-context", "How's my recovery?", "--days", "14"])
    def test_debug_context_command_prints_agent_context(
        self,
        coach_agent,
        strava_client,
        print_,
    ) -> None:
        client = Mock()
        strava_client.return_value = client
        coach = Mock()
        coach.debug_context.return_value = "Debug context"
        coach_agent.return_value = coach

        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        coach_agent.assert_called_once_with(lookback_days=14, strava_client=client)
        coach.debug_context.assert_called_once_with("How's my recovery?")
        print_.assert_called_once_with("Debug context")


if __name__ == "__main__":
    unittest.main()
