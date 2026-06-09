from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from running_agent.coach_agent import COMMANDS, CoachAgent, help_text

METERS_PER_MILE = 1609.344


class CoachAgentTest(unittest.TestCase):
    def test_handle_message_returns_replies_without_transport(self) -> None:
        agent = CoachAgent(strava_client=_FakeStrava())

        self.assertEqual(agent.handle_message("/ping"), ["Pong!"])

    @patch.object(CoachAgent, "training_summary", return_value="Recent summary")
    def test_command_aliases_route_to_same_handler(self, _training_summary) -> None:
        agent = CoachAgent(strava_client=_FakeStrava())

        self.assertEqual(agent.handle_message("/summary"), ["Recent summary"])

    def test_help_text_is_generated_from_command_registry(self) -> None:
        text = help_text()

        self.assertIn("/recent - summarize recent training", text)
        self.assertIn("/plan - show the current weekly plan", text)
        self.assertIn("/goal - show the current overall training goal", text)
        self.assertIn("/preferences - show remembered coaching notes", text)
        self.assertNotIn("/last -", text)
        self.assertNotIn("/run YYYY-MM-DD -", text)
        self.assertNotIn("/suggestplan -", text)
        self.assertNotIn("/setplan <plan> -", text)
        self.assertNotIn("/setgoal <goal> -", text)
        self.assertNotIn("/preference <note> -", text)
        self.assertNotIn("/garmin -", text)
        self.assertNotIn("/garminweek -", text)
        self.assertNotIn("/tick -", text)
        self.assertNotIn("/start -", text)
        for command in COMMANDS:
            if command.show_in_help:
                self.assertIn(command.usage or command.names[0], text)

    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 4, 0))
    def test_tick_returns_messages_without_transport(self, _coach_now) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        self.assertEqual(agent.tick(), [])
        self.assertEqual(state["last_strava_recent_refresh_hour"], "2026-06-01T04")
        self.assertTrue(saves)

    @patch("running_agent.coach_agent.current_garmin_context", return_value="Garmin context")
    @patch(
        "running_agent.coach_agent.coaching_reply",
        return_value="Nice work on that 5-mile run.",
    )
    def test_last_run_summary_passes_current_garmin_context(
        self,
        coaching_reply,
        _current_garmin_context,
    ) -> None:
        run = _run(1, "Easy Run", "2026-05-30T06:00:00Z")
        agent = CoachAgent(
            strava_client=_FakeStrava(activities=[run], latest=run, detailed={1: run})
        )

        note = agent.last_run_summary()

        self.assertEqual(note, "Nice work on that 5-mile run.")
        self.assertEqual(coaching_reply.call_args.kwargs["garmin_context"], "Garmin context")

    @patch("running_agent.coach_agent.append_run_result")
    @patch("running_agent.coach_agent.save_synced_run_detail")
    @patch("running_agent.coach_agent.current_garmin_context", return_value="Garmin context")
    @patch(
        "running_agent.coach_agent.coaching_reply",
        return_value="Nice work on that workout.",
    )
    def test_new_run_summary_passes_current_garmin_context(
        self,
        coaching_reply,
        _current_garmin_context,
        save_synced_run_detail,
        _append_run_result,
    ) -> None:
        run = _run(2, "Workout", "2026-05-30T06:00:00Z")
        agent = CoachAgent(
            strava_client=_FakeStrava(activities=[run], latest=run, detailed={2: run}),
            state={"seen_activity_ids": []},
        )

        messages = agent.check_new_runs(force=True)

        self.assertEqual(messages, ["Nice work on that workout."])
        save_synced_run_detail.assert_called_once_with(run, run)
        self.assertEqual(coaching_reply.call_args.kwargs["garmin_context"], "Garmin context")

    @patch("running_agent.coach_agent.refresh_garmin_snapshots")
    @patch("running_agent.coach_agent.coach_now")
    @patch("running_agent.coach_agent.generate_coach_reflection")
    @patch("running_agent.coach_agent.should_send_evening_report", return_value=False)
    @patch("running_agent.coach_agent.has_planned_workout_for_date", return_value=False)
    @patch(
        "running_agent.coach_agent.weekly_coaching_message",
        return_value="You had a great week. Here is next week.",
    )
    def test_tick_uses_integrated_weekly_coaching_message(
        self,
        weekly_coaching_message,
        _has_planned_workout_for_date,
        _should_send_evening_report,
        generate_coach_reflection,
        coach_now,
        _refresh_garmin_snapshots,
    ) -> None:
        coach_now.return_value = datetime(2026, 5, 31, 19, 0)
        state: dict = {}
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
        )

        messages = agent.tick()

        self.assertEqual(messages, ["You had a great week. Here is next week."])
        weekly_coaching_message.assert_called_once()
        kwargs = weekly_coaching_message.call_args.kwargs
        self.assertEqual(kwargs["week_start"].isoformat(), "2026-05-25")
        self.assertEqual(kwargs["target_week_start"].isoformat(), "2026-06-01")
        self.assertEqual(kwargs["lookback_days"], 42)
        generate_coach_reflection.assert_called_once()
        self.assertEqual(state["last_coach_reflection_attempt_date"], "2026-05-31")
        self.assertEqual(state["last_coach_reflection_date"], "2026-05-31")
        self.assertEqual(state["last_next_week_plan_start"], "2026-06-01")

    @patch("running_agent.coach_agent.refresh_garmin_snapshots")
    @patch("running_agent.coach_agent.coach_now")
    @patch("running_agent.coach_agent.generate_coach_reflection", side_effect=RuntimeError("nope"))
    @patch("running_agent.coach_agent.should_send_evening_report", return_value=False)
    @patch("running_agent.coach_agent.has_planned_workout_for_date", return_value=False)
    @patch(
        "running_agent.coach_agent.weekly_coaching_message",
        return_value="You had a great week. Here is next week.",
    )
    def test_sunday_message_still_sends_when_reflection_refresh_fails(
        self,
        _weekly_coaching_message,
        _has_planned_workout_for_date,
        _should_send_evening_report,
        _generate_coach_reflection,
        coach_now,
        _refresh_garmin_snapshots,
    ) -> None:
        coach_now.return_value = datetime(2026, 5, 31, 19, 0)
        state: dict = {}
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
        )

        messages = agent.tick()

        self.assertEqual(messages, ["You had a great week. Here is next week."])
        self.assertEqual(state["last_coach_reflection_attempt_date"], "2026-05-31")
        self.assertEqual(state["last_coach_reflection_error"], "nope")
        self.assertEqual(state["last_next_week_plan_start"], "2026-06-01")

    @patch("running_agent.coach_agent.generate_coach_reflection")
    @patch("running_agent.coach_agent.end_of_day_report", return_value="Evening note")
    @patch("running_agent.coach_agent.should_send_evening_report", return_value=True)
    @patch("running_agent.coach_agent.should_send_daily_checkin", return_value=False)
    @patch("running_agent.coach_agent.refresh_garmin_snapshots")
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 20, 30))
    def test_tick_sends_evening_report_if_due(
        self,
        _coach_now,
        _refresh_garmin_snapshots,
        _should_send_daily_checkin,
        _should_send_evening_report,
        end_of_day_report,
        _generate_coach_reflection,
    ) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(runs_by_date={"2026-06-01": [{"id": 1}]}),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        messages = agent.tick()

        self.assertEqual(messages, ["Evening note"])
        end_of_day_report.assert_called_once()
        self.assertEqual(state["last_evening_report_date"], "2026-06-01")
        self.assertTrue(saves)

    @patch(
        "running_agent.coach_agent.daily_workout_checkin", side_effect=RuntimeError("OpenAI 503")
    )
    @patch("running_agent.coach_agent.has_planned_workout_for_date", return_value=True)
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 9, 30))
    def test_daily_checkin_failure_does_not_mark_sent(
        self,
        _coach_now,
        _has_planned_workout_for_date,
        daily_workout_checkin,
    ) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        message = agent.daily_checkin_if_due()

        self.assertIsNone(message)
        daily_workout_checkin.assert_called_once()
        self.assertEqual(state["last_daily_checkin_error"], "OpenAI 503")
        self.assertNotIn("last_daily_checkin_date", state)
        self.assertTrue(saves)

    @patch("running_agent.coach_agent.end_of_day_report", side_effect=RuntimeError("OpenAI 503"))
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 20, 30))
    def test_evening_report_failure_does_not_mark_sent(
        self,
        _coach_now,
        end_of_day_report,
    ) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(runs_by_date={"2026-06-01": [{"id": 1}]}),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        message = agent.evening_report_if_due()

        self.assertIsNone(message)
        end_of_day_report.assert_called_once()
        self.assertEqual(state["last_evening_report_error"], "OpenAI 503")
        self.assertNotIn("last_evening_report_date", state)
        self.assertTrue(saves)

    @patch(
        "running_agent.coach_agent.weekly_coaching_message", side_effect=RuntimeError("OpenAI 503")
    )
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 7, 18, 0))
    def test_sunday_plan_failure_does_not_mark_sent(
        self,
        _coach_now,
        weekly_coaching_message,
    ) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        message = agent.sunday_plan_if_due()

        self.assertIsNone(message)
        weekly_coaching_message.assert_called_once()
        self.assertEqual(state["last_sunday_plan_error"], "OpenAI 503")
        self.assertNotIn("last_next_week_plan_start", state)
        self.assertTrue(saves)

    @patch("running_agent.coach_agent.generate_coach_reflection")
    @patch("running_agent.coach_agent.end_of_day_report", return_value="Evening note")
    @patch("running_agent.coach_agent.should_send_evening_report", return_value=True)
    @patch("running_agent.coach_agent.should_send_daily_checkin", return_value=False)
    @patch("running_agent.coach_agent.refresh_garmin_snapshots")
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 20, 30))
    def test_tick_suppresses_evening_report_without_completed_run(
        self,
        _coach_now,
        _refresh_garmin_snapshots,
        _should_send_daily_checkin,
        _should_send_evening_report,
        end_of_day_report,
        _generate_coach_reflection,
    ) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        messages = agent.tick()

        self.assertEqual(messages, [])
        end_of_day_report.assert_not_called()
        self.assertEqual(state["last_evening_report_date"], "2026-06-01")
        self.assertTrue(saves)

    @patch("running_agent.coach_agent.generate_coach_reflection")
    @patch("running_agent.coach_agent.refresh_garmin_snapshots")
    @patch("running_agent.coach_agent.should_send_evening_report", return_value=False)
    @patch("running_agent.coach_agent.should_send_daily_checkin", return_value=False)
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 19, 0))
    def test_tick_refreshes_coach_reflection_once_per_day(
        self,
        _coach_now,
        _should_send_daily_checkin,
        _should_send_evening_report,
        _refresh_garmin_snapshots,
        generate_coach_reflection,
    ) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        agent.tick()
        agent.tick()

        generate_coach_reflection.assert_called_once_with(agent.strava, lookback_days=42)
        self.assertEqual(state["last_coach_reflection_attempt_date"], "2026-06-01")
        self.assertEqual(state["last_coach_reflection_date"], "2026-06-01")
        self.assertTrue(saves)

    @patch("running_agent.coach_agent.generate_coach_reflection")
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 18, 59))
    def test_coach_reflection_refresh_waits_until_evening(
        self,
        _coach_now,
        generate_coach_reflection,
    ) -> None:
        state: dict = {}
        agent = CoachAgent(strava_client=_FakeStrava(), state=state)

        agent.refresh_coach_reflection_if_due()

        generate_coach_reflection.assert_not_called()
        self.assertNotIn("last_coach_reflection_attempt_date", state)

    @patch("running_agent.coach_agent.generate_coach_reflection", side_effect=RuntimeError("nope"))
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 19, 0))
    def test_coach_reflection_refresh_failure_is_not_retried_until_tomorrow(
        self,
        _coach_now,
        generate_coach_reflection,
    ) -> None:
        state: dict = {}
        agent = CoachAgent(strava_client=_FakeStrava(), state=state)

        agent.refresh_coach_reflection_if_due()
        agent.refresh_coach_reflection_if_due()

        generate_coach_reflection.assert_called_once_with(agent.strava, lookback_days=42)
        self.assertEqual(state["last_coach_reflection_attempt_date"], "2026-06-01")
        self.assertEqual(state["last_coach_reflection_error"], "nope")
        self.assertNotIn("last_coach_reflection_date", state)

    @patch("running_agent.coach_agent.coach_today", return_value=datetime(2026, 6, 4).date())
    @patch(
        "running_agent.coach_agent.weekly_plan_context_for_date",
        return_value="Matched Thursday plan context",
    )
    @patch("running_agent.coach_agent.training_goal_context", return_value="Goal")
    @patch("running_agent.coach_agent.coaching_reply", return_value="Recovery is steady.")
    def test_coach_reply_passes_today_plan_context(
        self,
        coaching_reply,
        _training_goal_context,
        weekly_plan_context_for_date,
        _coach_today,
    ) -> None:
        agent = CoachAgent(strava_client=_FakeStrava())

        reply = agent.coach_reply("How's my recovery?")

        self.assertEqual(reply, "Recovery is steady.")
        weekly_plan_context_for_date.assert_called_once_with(datetime(2026, 6, 4).date())
        self.assertEqual(
            coaching_reply.call_args.kwargs["weekly_plan"],
            "Matched Thursday plan context",
        )

    @patch("running_agent.coach_agent.coach_today", return_value=datetime(2026, 6, 4).date())
    @patch(
        "running_agent.coach_agent.weekly_plan_context_for_date",
        return_value="Matched Thursday plan context",
    )
    @patch("running_agent.coach_agent.training_goal_context", return_value="Goal")
    @patch("running_agent.coach_agent.image_coaching_reply", return_value="Course note")
    def test_coach_image_reply_passes_context_and_updates_conversation(
        self,
        image_coaching_reply,
        _training_goal_context,
        _weekly_plan_context_for_date,
        _coach_today,
    ) -> None:
        agent = CoachAgent(strava_client=_FakeStrava())

        reply = agent.coach_image_reply(
            caption="How should I pace this course?",
            image_bytes=b"image-bytes",
            mime_type="image/png",
        )

        self.assertEqual(reply, "Course note")
        self.assertEqual(image_coaching_reply.call_args.args[0], "How should I pace this course?")
        self.assertEqual(image_coaching_reply.call_args.kwargs["image_bytes"], b"image-bytes")
        self.assertEqual(image_coaching_reply.call_args.kwargs["mime_type"], "image/png")
        self.assertEqual(
            image_coaching_reply.call_args.kwargs["weekly_plan"],
            "Matched Thursday plan context",
        )
        self.assertEqual(
            agent.conversation[-2]["content"], "[image] How should I pace this course?"
        )
        self.assertEqual(agent.conversation[-1]["content"], "Course note")

    @patch("running_agent.coach_agent.coaching_reply")
    @patch(
        "running_agent.coach_agent.build_chat_debug_context",
        return_value="Debug object",
    )
    @patch(
        "running_agent.coach_agent.format_chat_debug_context",
        return_value="Debug context",
    )
    def test_debug_context_does_not_call_model(
        self,
        format_chat_debug_context,
        build_chat_debug_context,
        coaching_reply,
    ) -> None:
        agent = CoachAgent(strava_client=_FakeStrava())

        text = agent.debug_context("How's my recovery?")

        self.assertEqual(text, "Debug context")
        build_chat_debug_context.assert_called_once_with(
            message="How's my recovery?",
            client=agent.strava,
            lookback_days=agent.lookback_days,
            conversation=agent.conversation,
            tools_enabled=True,
        )
        format_chat_debug_context.assert_called_once_with("Debug object")
        coaching_reply.assert_not_called()

    @patch(
        "running_agent.coach_agent.sync_strava_runs",
        return_value={"runs_seen": 1, "summaries_saved": 1, "details_fetched": 0},
    )
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 9, 9, 15))
    def test_recent_strava_summary_refresh_runs_once_per_hour(
        self,
        _coach_now,
        sync_strava_runs,
    ) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        agent.refresh_recent_strava_summaries_if_due()
        agent.refresh_recent_strava_summaries_if_due()

        sync_strava_runs.assert_called_once_with(agent.strava, days=1)
        self.assertEqual(state["last_strava_recent_refresh_hour"], "2026-06-09T09")
        self.assertTrue(saves)

    @patch("running_agent.coach_agent.sync_strava_runs", side_effect=RuntimeError("strava down"))
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 9, 9, 15))
    def test_recent_strava_summary_refresh_failure_retries_next_tick(
        self,
        _coach_now,
        sync_strava_runs,
    ) -> None:
        state: dict = {}
        agent = CoachAgent(strava_client=_FakeStrava(), state=state)

        agent.refresh_recent_strava_summaries_if_due()
        agent.refresh_recent_strava_summaries_if_due()

        self.assertEqual(sync_strava_runs.call_count, 2)
        self.assertEqual(state["last_strava_recent_refresh_error"], "strava down")
        self.assertNotIn("last_strava_recent_refresh_hour", state)

    @patch("running_agent.coach_agent.refresh_garmin_snapshots")
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 5, 0))
    def test_garmin_cache_refresh_runs_once_per_day(
        self,
        _coach_now,
        refresh_garmin_snapshots,
    ) -> None:
        state: dict = {}
        agent = CoachAgent(strava_client=_FakeStrava(), state=state)

        agent.refresh_garmin_cache_if_due()
        agent.refresh_garmin_cache_if_due()

        refresh_garmin_snapshots.assert_called_once_with(days=45)
        self.assertEqual(state["last_garmin_refresh_attempt_date"], "2026-06-01")
        self.assertEqual(state["last_garmin_refresh_date"], "2026-06-01")

    @patch("running_agent.coach_agent.refresh_garmin_snapshots", side_effect=RuntimeError("nope"))
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 5, 0))
    def test_garmin_cache_refresh_failure_is_not_retried_until_tomorrow(
        self,
        _coach_now,
        refresh_garmin_snapshots,
    ) -> None:
        state: dict = {}
        agent = CoachAgent(strava_client=_FakeStrava(), state=state)

        agent.refresh_garmin_cache_if_due()
        agent.refresh_garmin_cache_if_due()

        refresh_garmin_snapshots.assert_called_once_with(days=45)
        self.assertEqual(state["last_garmin_refresh_attempt_date"], "2026-06-01")
        self.assertEqual(state["last_garmin_refresh_error"], "nope")
        self.assertNotIn("last_garmin_refresh_date", state)

    @patch("running_agent.coach_agent.refresh_garmin_snapshots")
    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 4, 59))
    def test_garmin_cache_refresh_waits_until_morning(
        self,
        _coach_now,
        refresh_garmin_snapshots,
    ) -> None:
        state: dict = {}
        agent = CoachAgent(strava_client=_FakeStrava(), state=state)

        agent.refresh_garmin_cache_if_due()

        refresh_garmin_snapshots.assert_not_called()
        self.assertNotIn("last_garmin_refresh_attempt_date", state)


class _FakeStrava:
    def __init__(
        self,
        activities: list[dict] | None = None,
        latest: dict | None = None,
        detailed: dict[int, dict] | None = None,
        runs_by_date: dict[str, list[dict]] | None = None,
    ):
        self.activities = activities or []
        self.latest = latest or {}
        self.detailed = detailed or {}
        self.runs_by_date = runs_by_date or {}

    def recent_activities(self, days: int) -> list[dict]:
        return self.activities

    def latest_run(self, days: int) -> dict:
        return self.latest

    def detailed_activity(self, activity_id: int) -> dict:
        return self.detailed[activity_id]

    def runs_on_date(self, target_date, search_days: int = 14) -> list[dict]:
        return self.runs_by_date.get(target_date.isoformat(), [])


def _run(activity_id: int, name: str, start_date_local: str) -> dict:
    return {
        "id": activity_id,
        "type": "Run",
        "name": name,
        "distance": 5 * METERS_PER_MILE,
        "moving_time": 40 * 60,
        "elapsed_time": 40 * 60,
        "start_date_local": start_date_local,
        "laps": [],
    }


if __name__ == "__main__":
    unittest.main()
