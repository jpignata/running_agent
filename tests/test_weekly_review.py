from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from running_agent.weekly_review import (
    current_week_start,
    review_week,
    reviewed_week_facts_context,
    weekly_coaching_message,
    weekly_quality_detail_context,
)

METERS_PER_MILE = 1609.344


class WeeklyReviewTest(unittest.TestCase):
    def test_current_week_start_returns_monday(self) -> None:
        self.assertEqual(current_week_start(datetime(2026, 5, 31).date()).isoformat(), "2026-05-25")

    @patch("running_agent.weekly_review.weekly_plan_history_for_week", return_value=None)
    @patch("running_agent.weekly_review.load_weekly_plan", return_value=None)
    @patch("running_agent.weekly_review.append_week_review")
    @patch("running_agent.weekly_review.save_goal_readiness_history_entry")
    @patch("running_agent.weekly_review.safe_garmin_weekly_context", return_value="Garmin weekly")
    @patch("running_agent.weekly_review.goal_readiness_context", return_value="Readiness")
    @patch("running_agent.weekly_review.goal_readiness_snapshot", return_value={"snapshot": True})
    @patch("running_agent.weekly_review.coach_log_context", return_value="Coach log")
    @patch(
        "running_agent.weekly_review.weekly_notes_context",
        return_value="No athlete notes were saved for the reviewed week.",
    )
    @patch("running_agent.weekly_review.training_goal_context", return_value="Goal")
    @patch("running_agent.weekly_review.weekly_plan_context_for_week", return_value="Weekly plan")
    @patch("running_agent.weekly_review.weekly_quality_detail_context", return_value="")
    @patch(
        "running_agent.weekly_review.coaching_reply", return_value="Good week. Keep it controlled."
    )
    def test_review_week_passes_context_and_logs_summary(
        self,
        coaching_reply,
        _weekly_quality_detail_context,
        weekly_plan_context_for_week,
        _training_goal_context,
        _weekly_notes_context,
        _coach_log_context,
        goal_readiness_snapshot,
        goal_readiness_context,
        _safe_garmin_weekly_context,
        save_goal_readiness_history_entry,
        append_week_review,
        _load_weekly_plan,
        _weekly_plan_history_for_week,
    ) -> None:
        review = review_week(
            _FakeStravaClient([_run("Easy Run")]),
            week_start=datetime(2026, 5, 25).date(),
        )

        self.assertEqual(review, "Good week. Keep it controlled.")
        kwargs = coaching_reply.call_args.kwargs
        self.assertEqual(kwargs["weekly_plan"], "Reviewed-week plan:\nWeekly plan")
        self.assertIn("Reviewed-week deterministic facts:", kwargs["recent_runs"])
        self.assertIn("Completed synced mileage in reviewed window: 5.0 mi.", kwargs["recent_runs"])
        self.assertEqual(kwargs["training_goal"], "Goal")
        self.assertEqual(kwargs["goal_readiness"], "Readiness")
        self.assertIn("Athlete weekly notes:", kwargs["coach_log"])
        self.assertIn("No athlete notes were saved for the reviewed week.", kwargs["coach_log"])
        self.assertIn("Coach log:\nCoach log", kwargs["coach_log"])
        self.assertEqual(kwargs["garmin_context"], "Garmin weekly")
        self.assertFalse(kwargs["tools_enabled"])
        goal_readiness_snapshot.assert_called_once()
        self.assertEqual(goal_readiness_snapshot.call_args.kwargs["days"], 7)
        goal_readiness_context.assert_called_once_with({"snapshot": True})
        prompt = coaching_reply.call_args.args[0]
        self.assertIn("deterministic goal-readiness snapshot", prompt)
        self.assertIn("reviewed-week deterministic facts", prompt)
        self.assertIn("do not say the athlete was over plan", prompt)
        self.assertIn("what next checkpoint would raise confidence", prompt)
        weekly_plan_context_for_week.assert_called_once_with(
            datetime(2026, 5, 25).date(), prefer_history=True
        )
        append_week_review.assert_called_once_with(
            week_start="2026-05-25",
            week_end="2026-05-31",
            summary="Good week. Keep it controlled.",
        )
        save_goal_readiness_history_entry.assert_called_once_with(
            week_start="2026-05-25",
            snapshot={"snapshot": True},
        )

    @patch("running_agent.weekly_review.weekly_plan_history_for_week", return_value=None)
    @patch("running_agent.weekly_review.load_weekly_plan", return_value=None)
    @patch("running_agent.weekly_review.append_week_review")
    @patch("running_agent.weekly_review.save_goal_readiness_history_entry")
    @patch("running_agent.weekly_review.safe_garmin_weekly_context", return_value="Garmin weekly")
    @patch("running_agent.weekly_review.goal_readiness_context", return_value="Readiness")
    @patch("running_agent.weekly_review.goal_readiness_snapshot", return_value={"snapshot": True})
    @patch("running_agent.weekly_review.weekly_quality_detail_context", return_value="")
    @patch("running_agent.weekly_review.coaching_reply", side_effect=RuntimeError("offline"))
    def test_review_week_has_fallback(
        self,
        _coaching_reply,
        _weekly_quality_detail_context,
        _goal_readiness_snapshot,
        _goal_readiness_context,
        _garmin,
        save_goal_readiness_history_entry,
        append_week_review,
        _load_weekly_plan,
        _weekly_plan_history_for_week,
    ) -> None:
        review = review_week(
            _FakeStravaClient([_run("Easy Run")]),
            week_start=datetime(2026, 5, 25).date(),
        )

        self.assertIn("AI weekly review was unavailable (offline).", review)
        append_week_review.assert_called_once()
        save_goal_readiness_history_entry.assert_called_once()

    @patch("running_agent.weekly_review.weekly_plan_history_for_week", return_value=None)
    @patch("running_agent.weekly_review.load_weekly_plan", return_value=None)
    @patch("running_agent.weekly_review.append_week_review")
    @patch("running_agent.weekly_review.save_goal_readiness_history_entry")
    @patch("running_agent.weekly_review.safe_garmin_weekly_context", return_value="Garmin weekly")
    @patch("running_agent.weekly_review.goal_readiness_context", return_value="Readiness")
    @patch("running_agent.weekly_review.goal_readiness_snapshot", return_value={"snapshot": True})
    @patch("running_agent.weekly_review.coach_log_context", return_value="Coach log")
    @patch(
        "running_agent.weekly_review.weekly_notes_context",
        return_value="Athlete notes for reviewed week:\n- moved long run to Sunday",
    )
    @patch("running_agent.weekly_review.training_goal_context", return_value="Goal")
    @patch(
        "running_agent.weekly_review.weekly_plan_context_for_week",
        side_effect=[
            "Saved reviewed-week plan:\nMonday 5 easy",
            "Saved target-week plan:\nMonday 6 easy",
        ],
    )
    @patch("running_agent.weekly_review.weekly_quality_detail_context", return_value="")
    @patch(
        "running_agent.weekly_review.coaching_reply",
        return_value="You had a great week. Next week, keep it controlled.",
    )
    def test_weekly_coaching_message_combines_review_and_plan(
        self,
        coaching_reply,
        _weekly_quality_detail_context,
        _weekly_plan_context_for_week,
        _training_goal_context,
        _weekly_notes_context,
        _coach_log_context,
        goal_readiness_snapshot,
        goal_readiness_context,
        _safe_garmin_weekly_context,
        save_goal_readiness_history_entry,
        append_week_review,
        _load_weekly_plan,
        _weekly_plan_history_for_week,
    ) -> None:
        message = weekly_coaching_message(
            _FakeStravaClient([_run("Easy Run")]),
            week_start=datetime(2026, 5, 25).date(),
            target_week_start=datetime(2026, 6, 1).date(),
        )

        self.assertEqual(message, "You had a great week. Next week, keep it controlled.")
        kwargs = coaching_reply.call_args.kwargs
        self.assertEqual(
            kwargs["weekly_plan"],
            "Reviewed-week plan:\nSaved reviewed-week plan:\nMonday 5 easy\n\n"
            "Target-week plan:\nSaved target-week plan:\nMonday 6 easy",
        )
        self.assertIn("Reviewed-week deterministic facts:", kwargs["recent_runs"])
        self.assertIn("Completed versus planned mileage: unavailable.", kwargs["recent_runs"])
        self.assertEqual(kwargs["goal_readiness"], "Readiness")
        self.assertIn("Athlete weekly notes:", kwargs["coach_log"])
        self.assertIn("moved long run to Sunday", kwargs["coach_log"])
        self.assertIn("Coach log:\nCoach log", kwargs["coach_log"])
        self.assertFalse(kwargs["tools_enabled"])
        goal_readiness_snapshot.assert_called_once()
        self.assertEqual(goal_readiness_snapshot.call_args.kwargs["days"], 42)
        goal_readiness_context.assert_called_once_with({"snapshot": True})
        prompt = coaching_reply.call_args.args[0]
        self.assertIn("recap that saved plan instead of suggesting a different one", prompt)
        self.assertIn("Use the labeled reviewed-week plan only", prompt)
        self.assertIn("Use the labeled target-week plan only", prompt)
        self.assertIn("deterministic goal-readiness snapshot", prompt)
        self.assertIn("reviewed-week deterministic facts", prompt)
        self.assertEqual(
            _weekly_plan_context_for_week.call_args_list[0].args,
            (datetime(2026, 5, 25).date(),),
        )
        self.assertEqual(
            _weekly_plan_context_for_week.call_args_list[0].kwargs,
            {"prefer_history": True},
        )
        self.assertEqual(
            _weekly_plan_context_for_week.call_args_list[1].args,
            (datetime(2026, 6, 1).date(),),
        )
        self.assertEqual(_weekly_plan_context_for_week.call_args_list[1].kwargs, {})
        append_week_review.assert_called_once_with(
            week_start="2026-05-25",
            week_end="2026-05-31",
            summary="You had a great week. Next week, keep it controlled.",
        )
        save_goal_readiness_history_entry.assert_called_once_with(
            week_start="2026-05-25",
            snapshot={"snapshot": True},
        )

    @patch("running_agent.weekly_review.weekly_plan_history_for_week", return_value=None)
    @patch("running_agent.weekly_review.load_weekly_plan", return_value=None)
    @patch("running_agent.weekly_review.append_week_review")
    @patch("running_agent.weekly_review.save_goal_readiness_history_entry")
    @patch("running_agent.weekly_review.safe_garmin_weekly_context", return_value="Garmin weekly")
    @patch("running_agent.weekly_review.goal_readiness_context", return_value="Readiness")
    @patch("running_agent.weekly_review.goal_readiness_snapshot", return_value={"snapshot": True})
    @patch("running_agent.weekly_review.coach_log_context", return_value="Coach log")
    @patch("running_agent.weekly_review.weekly_notes_context", return_value="No notes")
    @patch("running_agent.weekly_review.training_goal_context", return_value="Goal")
    @patch(
        "running_agent.weekly_review.weekly_plan_context_for_week", return_value="No target plan"
    )
    @patch("running_agent.weekly_review.weekly_quality_detail_context", return_value="")
    @patch("running_agent.weekly_review.coaching_reply", side_effect=RuntimeError("offline"))
    def test_weekly_coaching_message_raises_when_model_is_unavailable(
        self,
        _coaching_reply,
        _weekly_quality_detail_context,
        _weekly_plan_context_for_week,
        _training_goal_context,
        _weekly_notes_context,
        _coach_log_context,
        _goal_readiness_snapshot,
        _goal_readiness_context,
        _safe_garmin_weekly_context,
        save_goal_readiness_history_entry,
        append_week_review,
        _load_weekly_plan,
        _weekly_plan_history_for_week,
    ) -> None:
        with self.assertRaisesRegex(RuntimeError, "offline"):
            weekly_coaching_message(
                _FakeStravaClient([_run("Easy Run")]),
                week_start=datetime(2026, 5, 25).date(),
                target_week_start=datetime(2026, 6, 1).date(),
            )

        append_week_review.assert_not_called()
        save_goal_readiness_history_entry.assert_not_called()

    @patch("running_agent.weekly_review.planned_workout_for_date", return_value="4x1200m + 4x400m")
    def test_weekly_quality_detail_context_fetches_laps_for_planned_workout(
        self, _planned_workout
    ) -> None:
        run = _run("Track")
        run["id"] = 123
        client = _FakeStravaClient([run])
        client.details[123] = {
            **run,
            "laps": [
                {
                    "lap_index": 1,
                    "distance": 0.75 * METERS_PER_MILE,
                    "moving_time": 5 * 60,
                    "elapsed_time": 5 * 60,
                }
            ],
        }

        context = weekly_quality_detail_context(
            client,
            [run],
            week_start=datetime(2026, 5, 25).date(),
            week_end=datetime(2026, 5, 31).date(),
        )

        self.assertIn("Lap data from Strava detailed activity", context)
        self.assertEqual(client.detailed_activity_ids, [123])

    @patch("running_agent.weekly_review.planned_workout_for_date", return_value="easy 5")
    def test_weekly_quality_detail_context_skips_easy_runs(self, _planned_workout) -> None:
        run = _run("Easy Run")
        run["id"] = 123
        client = _FakeStravaClient([run])

        context = weekly_quality_detail_context(
            client,
            [run],
            week_start=datetime(2026, 5, 25).date(),
            week_end=datetime(2026, 5, 31).date(),
        )

        self.assertEqual(context, "")
        self.assertEqual(client.detailed_activity_ids, [])

    @patch("running_agent.weekly_review.weekly_plan_history_for_week", return_value=None)
    @patch(
        "running_agent.weekly_review.load_weekly_plan",
        return_value={
            "week_start": "2026-05-25",
            "updated_at": "2026-05-24T12:00:00+00:00",
            "text": "\n".join(
                [
                    "Monday 5 easy",
                    "Tuesday rest",
                    "Wednesday 6 miles with strides",
                    "Friday 4 mi recovery",
                    "Sunday 10 long",
                ]
            ),
        },
    )
    def test_reviewed_week_facts_include_completed_and_planned_mileage(
        self, _load_weekly_plan, _weekly_plan_history_for_week
    ) -> None:
        context = reviewed_week_facts_context(
            [
                _run("Monday", start_date_local="2026-05-25T06:00:00Z", miles=5),
                _run("Wednesday", start_date_local="2026-05-27T06:00:00Z", miles=6),
                _run("Sunday", start_date_local="2026-05-31T06:00:00Z", miles=10),
                _run("Next week", start_date_local="2026-06-01T06:00:00Z", miles=5),
                {"type": "Ride", "distance": 20 * METERS_PER_MILE},
            ],
            datetime(2026, 5, 25).date(),
            datetime(2026, 5, 31).date(),
        )

        self.assertIn("Completed synced runs in reviewed window: 3.", context)
        self.assertIn("Completed synced mileage in reviewed window: 21.0 mi.", context)
        self.assertIn("Explicit planned mileage: 25.0 mi.", context)
        self.assertIn("Completed minus explicit planned mileage: -4.0 mi.", context)

    @patch("running_agent.weekly_review.weekly_plan_history_for_week", return_value=None)
    @patch(
        "running_agent.weekly_review.load_weekly_plan",
        return_value={
            "week_start": "2026-06-01",
            "updated_at": "2026-05-31T12:00:00+00:00",
            "text": "Monday 5 easy",
        },
    )
    def test_reviewed_week_facts_refuse_future_plan_comparison(
        self, _load_weekly_plan, _weekly_plan_history_for_week
    ) -> None:
        context = reviewed_week_facts_context(
            [_run("Easy Run", start_date_local="2026-05-25T06:00:00Z", miles=5)],
            datetime(2026, 5, 25).date(),
            datetime(2026, 5, 31).date(),
        )

        self.assertIn("no saved plan explicitly applies to the reviewed week", context)
        self.assertIn("Explicit planned mileage: unavailable.", context)
        self.assertIn("Completed versus planned mileage: unavailable.", context)

    @patch(
        "running_agent.weekly_review.weekly_plan_history_for_week",
        return_value={
            "week_start": "2026-05-25",
            "updated_at": "2026-05-24T12:00:00+00:00",
            "text": "Monday 5 easy",
        },
    )
    @patch(
        "running_agent.weekly_review.load_weekly_plan",
        return_value={
            "week_start": "2026-06-01",
            "updated_at": "2026-05-31T12:00:00+00:00",
            "text": "Monday 10 future",
        },
    )
    def test_reviewed_week_facts_prefer_history_over_active_plan(
        self, _load_weekly_plan, _weekly_plan_history_for_week
    ) -> None:
        context = reviewed_week_facts_context(
            [_run("Easy Run", start_date_local="2026-05-25T06:00:00Z", miles=5)],
            datetime(2026, 5, 25).date(),
            datetime(2026, 5, 31).date(),
        )

        self.assertIn("Explicit planned mileage: 5.0 mi.", context)
        self.assertIn("Completed minus explicit planned mileage: +0.0 mi.", context)
        self.assertNotIn("10 future", context)

    @patch("running_agent.weekly_review.weekly_plan_history_for_week", return_value=None)
    @patch(
        "running_agent.weekly_review.load_weekly_plan",
        return_value={
            "week_start": "2026-05-25",
            "updated_at": "2026-05-24T12:00:00+00:00",
            "text": "Tuesday 2mi WU, 4x1200m, CD\nWednesday 4x1200m\nSaturday long run",
        },
    )
    def test_reviewed_week_facts_treat_ambiguous_plan_mileage_as_unavailable(
        self, _load_weekly_plan, _weekly_plan_history_for_week
    ) -> None:
        context = reviewed_week_facts_context(
            [_run("Workout", start_date_local="2026-05-27T06:00:00Z", miles=7)],
            datetime(2026, 5, 25).date(),
            datetime(2026, 5, 31).date(),
        )

        self.assertIn("reviewed-week plan exists", context)
        self.assertIn("planned mileage is not explicit for Tuesday, Wednesday, Saturday", context)
        self.assertIn("Explicit planned mileage: unavailable.", context)


class _FakeStravaClient:
    def __init__(self, activities: list[dict]):
        self.activities = activities
        self.details: dict[int, dict] = {}
        self.detailed_activity_ids: list[int] = []

    def recent_activities(self, days: int) -> list[dict]:
        return self.activities

    def detailed_activity(self, activity_id: int) -> dict:
        self.detailed_activity_ids.append(activity_id)
        return self.details[activity_id]


def _run(
    name: str,
    start_date_local: str = "2026-05-29T06:00:00Z",
    miles: float = 5,
) -> dict:
    return {
        "id": 1,
        "type": "Run",
        "name": name,
        "distance": miles * METERS_PER_MILE,
        "moving_time": int(miles * 8 * 60),
        "start_date_local": start_date_local,
    }


if __name__ == "__main__":
    unittest.main()
