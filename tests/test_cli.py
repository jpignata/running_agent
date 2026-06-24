from __future__ import annotations

import os
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
    @patch("running_agent.cli.format_local_store_health", return_value="Store health")
    @patch("running_agent.cli.local_store_health", return_value={"activity_count": 2})
    @patch("running_agent.cli.StravaClient")
    @patch("sys.argv", ["running-agent", "strava-store-health"])
    def test_strava_store_health_command_reports_local_store_without_network(
        self,
        strava_client,
        local_store_health,
        format_local_store_health,
        print_,
    ) -> None:
        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        strava_client.assert_not_called()
        local_store_health.assert_called_once_with()
        format_local_store_health.assert_called_once_with({"activity_count": 2})
        print_.assert_called_once_with("Store health")

    @patch("builtins.print")
    @patch("running_agent.cli.run_memory_context", return_value="Run memory context")
    @patch(
        "running_agent.cli.validate_run_memory",
        return_value={
            "ok": True,
            "feedback_entries": 1,
            "run_records": 2,
            "missing_feedback": [],
            "stale_feedback": [],
        },
    )
    @patch(
        "running_agent.cli.refresh_run_memory",
        return_value={"runs": [{"activity_id": 1}, {"activity_id": 2}]},
    )
    @patch("running_agent.cli.StravaClient")
    @patch(
        "running_agent.cli.sync_strava_runs",
        return_value={"runs_seen": 2, "summaries_saved": 2, "details_fetched": 1},
    )
    @patch("sys.argv", ["running-agent", "run-memory", "--days", "21", "--sync", "--validate"])
    def test_run_memory_command_syncs_refreshes_and_prints_context(
        self,
        sync_strava_runs,
        strava_client,
        refresh_run_memory,
        validate_run_memory,
        run_memory_context,
        print_,
    ) -> None:
        client = Mock()
        strava_client.return_value = client

        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        sync_strava_runs.assert_called_once_with(client, days=21)
        refresh_run_memory.assert_called_once_with(days=21)
        run_memory_context.assert_called_once_with([{"activity_id": 1}, {"activity_id": 2}])
        validate_run_memory.assert_called_once_with(
            records=[{"activity_id": 1}, {"activity_id": 2}]
        )
        self.assertEqual(
            [call.args[0] for call in print_.call_args_list],
            [
                "Synced 2 Strava runs; saved 2 summaries; fetched 1 detailed activities.",
                "Refreshed run memory with 2 runs over 21 days.",
                "Run memory context",
                "Run memory validation: OK\nFeedback entries: 1\nRun records: 2",
            ],
        )

    @patch("builtins.print")
    @patch("running_agent.cli.run_memory_context", return_value="Run memory context")
    @patch(
        "running_agent.cli.validate_run_memory",
        return_value={
            "ok": False,
            "feedback_entries": 1,
            "run_records": 0,
            "missing_feedback": [{"run_date": "2026-06-19", "activity_id": 123, "raw": "RPE 3"}],
            "stale_feedback": [],
        },
    )
    @patch("running_agent.cli.refresh_run_memory", return_value={"runs": []})
    @patch("sys.argv", ["running-agent", "run-memory", "--validate"])
    def test_run_memory_command_returns_failure_when_validation_fails(
        self,
        _refresh_run_memory,
        _validate_run_memory,
        _run_memory_context,
        print_,
    ) -> None:
        exit_code = cli._main()

        self.assertEqual(exit_code, 1)
        self.assertIn("Run memory validation: FAILED", print_.call_args_list[-1].args[0])
        self.assertIn("Missing feedback mappings: 1", print_.call_args_list[-1].args[0])

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

    @patch("builtins.print")
    @patch("running_agent.cli.boot_linger_hint", return_value="linger hint")
    @patch("running_agent.cli.install_telegram_user_service", return_value="/tmp/service")
    @patch("sys.argv", ["running-agent", "install-telegram-service", "--no-start"])
    def test_install_telegram_service_command_installs_user_service(
        self,
        install_telegram_user_service,
        _boot_linger_hint,
        print_,
    ) -> None:
        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        install_telegram_user_service.assert_called_once_with(enable=True, start=False)
        self.assertEqual(
            [call.args for call in print_.call_args_list],
            [
                ("Installed Telegram service: /tmp/service",),
                ("Enabled user service: running-agent-telegram.service",),
                ("linger hint",),
            ],
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("running_agent.cli.save_agent_state")
    @patch("running_agent.cli.load_agent_state", return_value={})
    @patch("running_agent.cli.ReplTransport")
    @patch("running_agent.cli.CoachAgent")
    @patch("sys.argv", ["running-agent", "repl", "--trace-log"])
    def test_repl_trace_log_sets_trace_env(
        self,
        coach_agent,
        repl_transport,
        _load_agent_state,
        _save_agent_state,
    ) -> None:
        repl_transport.return_value.run.return_value = None

        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(os.environ["RUNNING_AGENT_TRACE_LOG"], "1")
        self.assertNotIn("RUNNING_AGENT_QUIET_LOG", os.environ)
        repl_transport.assert_called_once_with(coach_agent.return_value)

    @patch.dict(os.environ, {}, clear=True)
    @patch("running_agent.cli.TelegramTransport")
    @patch("sys.argv", ["running-agent", "telegram", "--trace-log"])
    def test_telegram_trace_log_sets_trace_env(self, telegram_transport) -> None:
        telegram_transport.return_value.run_forever.return_value = None

        exit_code = cli._main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(os.environ["RUNNING_AGENT_TRACE_LOG"], "1")
        telegram_transport.assert_called_once_with(poll_seconds=300, lookback_days=28)
        telegram_transport.return_value.run_forever.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
