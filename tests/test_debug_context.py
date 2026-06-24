from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from running_agent.debug_context import build_chat_debug_context, format_chat_debug_context


class DebugContextTest(unittest.TestCase):
    @patch("running_agent.debug_context.coach_today", return_value=date(2026, 6, 5))
    @patch("running_agent.debug_context.athlete_profile_context", return_value="Profile context")
    @patch("running_agent.debug_context.coach_reflection_context", return_value="Coach thesis")
    @patch("running_agent.debug_context.goal_readiness_context", return_value="Readiness context")
    @patch("running_agent.debug_context.training_goal_context", return_value="Goal context")
    @patch(
        "running_agent.debug_context.weekly_plan_context_for_date",
        return_value="Friday plan context",
    )
    def test_build_chat_debug_context_assembles_normal_reply_context(
        self,
        weekly_plan_context_for_date,
        _training_goal_context,
        goal_readiness_context,
        _coach_reflection_context,
        _athlete_profile_context,
        _coach_today,
    ) -> None:
        client = _FakeStrava([_run()])

        context = build_chat_debug_context(
            message="How's my recovery?",
            client=client,
            lookback_days=14,
            conversation=[{"role": "athlete", "content": "Yesterday?"}],
        )

        self.assertEqual(client.requested_days, 14)
        weekly_plan_context_for_date.assert_called_once_with(date(2026, 6, 5))
        self.assertEqual(context.message, "How's my recovery?")
        self.assertTrue(context.tools_enabled)
        self.assertIn("get_garmin_readiness", context.tool_names)
        self.assertEqual(context.weekly_plan, "Friday plan context")
        self.assertEqual(context.training_goal, "Goal context")
        self.assertEqual(context.goal_readiness, "Readiness context")
        self.assertEqual(context.athlete_profile, "Profile context")
        self.assertEqual(context.coach_reflection, "Coach thesis")
        self.assertGreater(context.prompt_diagnostics["input_chars"], 0)
        self.assertGreater(context.prompt_diagnostics["estimated_input_tokens"], 0)
        self.assertGreater(context.prompt_diagnostics["instructions_chars"], 0)
        self.assertGreater(context.prompt_diagnostics["tool_schema_chars"], 0)
        self.assertGreater(
            context.prompt_diagnostics["estimated_request_chars"],
            context.prompt_diagnostics["input_chars"],
        )
        self.assertEqual(
            context.prompt_diagnostics["weekly_plan_chars"], len("Friday plan context")
        )
        self.assertEqual(context.prompt_diagnostics["tool_count"], len(context.tool_names))
        goal_readiness_context.assert_called_once()
        self.assertEqual(goal_readiness_context.call_args.kwargs["days"], 14)
        self.assertIn("How's my recovery?", context.assembled_input)
        self.assertIn("Friday plan context", context.assembled_input)
        self.assertIn("Readiness context", context.assembled_input)
        self.assertIn("Profile context", context.assembled_input)
        self.assertIn("Coach thesis", context.assembled_input)

    @patch("running_agent.debug_context.coach_today", return_value=date(2026, 6, 5))
    @patch("running_agent.debug_context.athlete_profile_context", return_value="Profile context")
    @patch("running_agent.debug_context.coach_reflection_context", return_value="Coach thesis")
    @patch("running_agent.debug_context.goal_readiness_context", return_value="Readiness context")
    @patch("running_agent.debug_context.training_goal_context", return_value="Goal context")
    @patch(
        "running_agent.debug_context.weekly_plan_context_for_date",
        return_value="Friday plan context",
    )
    def test_format_chat_debug_context_prints_readable_sections(
        self,
        _weekly_plan_context_for_date,
        _training_goal_context,
        _goal_readiness_context,
        _coach_reflection_context,
        _athlete_profile_context,
        _coach_today,
    ) -> None:
        context = build_chat_debug_context(
            message="How's my recovery?",
            client=_FakeStrava([_run()]),
        )

        text = format_chat_debug_context(context)

        self.assertIn("## Debug Metadata", text)
        self.assertIn("Tools enabled: yes", text)
        self.assertIn("Prompt size:", text)
        self.assertIn("Estimated full request:", text)
        self.assertIn("instructions", text)
        self.assertIn("Section chars:", text)
        self.assertIn("tools.", text)
        self.assertIn("Garmin: not included in the initial prompt", text)
        self.assertIn("## User Message\nHow's my recovery?", text)
        self.assertIn("## Matched Weekly Plan\nFriday plan context", text)
        self.assertIn("## Goal Readiness\nReadiness context", text)
        self.assertIn("## Assembled Model Input", text)


class _FakeStrava:
    def __init__(self, activities: list[dict]):
        self.activities = activities
        self.requested_days: int | None = None

    def recent_activities(self, days: int) -> list[dict]:
        self.requested_days = days
        return self.activities


def _run() -> dict:
    return {
        "id": 1,
        "type": "Run",
        "name": "Easy Run",
        "distance": 5 * 1609.344,
        "moving_time": 42 * 60,
        "elapsed_time": 42 * 60,
        "start_date_local": "2026-06-05T07:00:00",
    }


if __name__ == "__main__":
    unittest.main()
