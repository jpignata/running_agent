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

    @patch("builtins.print")
    @patch("running_agent.cli.StravaClient")
    @patch("running_agent.cli.load_agent_state", return_value={"state": "value"})
    @patch("running_agent.cli.format_scheduled_preview", return_value="Preview text")
    @patch("running_agent.cli.preview_scheduled_message", return_value="Preview object")
    @patch("sys.argv", ["running-agent", "preview", "evening", "--date", "2026-06-05"])
    def test_preview_command_prints_scheduled_message_preview(
        self,
        preview_scheduled_message,
        format_scheduled_preview,
        load_agent_state,
        strava_client,
        print_,
    ) -> None:
        client = Mock()
        strava_client.return_value = client

        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        preview_scheduled_message.assert_called_once()
        kwargs = preview_scheduled_message.call_args.kwargs
        self.assertEqual(preview_scheduled_message.call_args.args, ("evening",))
        self.assertEqual(kwargs["client"], client)
        self.assertEqual(kwargs["target_date"].isoformat(), "2026-06-05")
        self.assertEqual(kwargs["state"], {"state": "value"})
        load_agent_state.assert_called_once()
        format_scheduled_preview.assert_called_once_with("Preview object")
        print_.assert_called_once_with("Preview text")

    @patch("running_agent.cli.eval_runner_main", return_value=0)
    @patch("sys.argv", ["running-agent", "evals", "--case", "adjust_existing_weekly_plan"])
    def test_evals_command_runs_eval_runner(self, eval_runner_main) -> None:
        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        eval_runner_main.assert_called_once_with(["--case", "adjust_existing_weekly_plan"])

    @patch("running_agent.cli.eval_runner_main", return_value=0)
    @patch("sys.argv", ["running-agent", "evals"])
    def test_evals_command_without_case_runs_all_evals(self, eval_runner_main) -> None:
        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        eval_runner_main.assert_called_once_with([])

    @patch("running_agent.cli.eval_runner_main", return_value=0)
    @patch(
        "sys.argv", ["running-agent", "evals", "--case", "adjust_existing_weekly_plan", "--debug"]
    )
    def test_evals_command_forwards_debug_flag(self, eval_runner_main) -> None:
        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        eval_runner_main.assert_called_once_with(
            ["--case", "adjust_existing_weekly_plan", "--debug"]
        )


if __name__ == "__main__":
    unittest.main()
