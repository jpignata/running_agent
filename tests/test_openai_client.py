from __future__ import annotations

import unittest
from unittest.mock import patch

from running_agent.openai_client import (
    coaching_reply,
    image_coaching_reply,
    normalize_post_run_feedback,
    resolve_pending_question,
)


class OpenAIClientTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "key", "OPENAI_SMALL_MODEL": "cheap-helper-model"},
        clear=True,
    )
    @patch(
        "running_agent.openai_client._post_json",
        return_value={
            "output_text": (
                '{"is_feedback": true, "rpe": 8, "legs": "Heavy", ' '"pain": "No", "notes": null}'
            )
        },
    )
    def test_normalize_post_run_feedback_uses_small_model(self, post_json) -> None:
        feedback = normalize_post_run_feedback("Felt like 8, heavy legs, no pain")

        self.assertEqual(
            feedback,
            {"is_feedback": True, "rpe": 8, "legs": "heavy", "pain": "no", "notes": None},
        )
        payload = post_json.call_args.args[1]
        self.assertEqual(payload["model"], "cheap-helper-model")
        self.assertIn("Return only JSON", payload["instructions"])
        self.assertEqual(payload["input"], "Felt like 8, heavy legs, no pain")
        self.assertEqual(payload["temperature"], 0)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "main-model"}, clear=True)
    @patch(
        "running_agent.openai_client._post_json",
        return_value={
            "output_text": (
                '{"is_feedback": false, "rpe": 7, "legs": "heavy", '
                '"pain": "no", "notes": "ignore"}'
            )
        },
    )
    def test_normalize_post_run_feedback_defaults_to_small_model(self, post_json) -> None:
        feedback = normalize_post_run_feedback("what should I do tomorrow?")

        self.assertEqual(
            feedback,
            {"is_feedback": False, "rpe": None, "legs": None, "pain": None, "notes": None},
        )
        self.assertEqual(post_json.call_args.args[1]["model"], "gpt-5.4-mini")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch(
        "running_agent.openai_client._post_json",
        return_value={
            "output_text": (
                "```json\n"
                '{"is_feedback": true, "rpe": 22, "legs": "", '
                '"pain": null, "notes": "Breathing fine"}\n'
                "```"
            )
        },
    )
    def test_normalize_post_run_feedback_validates_json_fields(self, _post_json) -> None:
        feedback = normalize_post_run_feedback("breathing was fine")

        self.assertEqual(
            feedback,
            {
                "is_feedback": True,
                "rpe": None,
                "legs": None,
                "pain": None,
                "notes": "breathing fine",
            },
        )

    @patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "key", "OPENAI_SMALL_MODEL": "tiny-model"},
        clear=True,
    )
    @patch(
        "running_agent.openai_client._post_json",
        return_value={
            "output_text": (
                '{"answers_question": true, "kind": "post_run_feedback", '
                '"confidence": 0.92, "extracted": {"rpe": 5, "legs": "Great", '
                '"pain": "No", "notes": null}}'
            )
        },
    )
    def test_resolve_pending_question_uses_small_model(self, post_json) -> None:
        result = resolve_pending_question(
            question="How did that run feel? Any pain or soreness?",
            response="rpe 5, legs great, no pain",
            kind="post_run_feedback",
        )

        self.assertEqual(
            result,
            {
                "answers_question": True,
                "kind": "post_run_feedback",
                "confidence": 0.92,
                "extracted": {
                    "is_feedback": True,
                    "rpe": 5,
                    "legs": "great",
                    "pain": "no",
                    "notes": None,
                },
            },
        )
        payload = post_json.call_args.args[1]
        self.assertEqual(payload["model"], "tiny-model")
        self.assertIn("pending question", payload["instructions"])
        self.assertIn("coach_question", payload["input"])
        self.assertEqual(payload["temperature"], 0)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key", "OPENAI_MODEL": "main-model"}, clear=True)
    @patch(
        "running_agent.openai_client._post_json",
        return_value={
            "output_text": (
                '{"answers_question": false, "kind": "post_run_feedback", '
                '"confidence": 0.1, "extracted": {}}'
            )
        },
    )
    def test_resolve_pending_question_defaults_to_small_model(self, post_json) -> None:
        resolve_pending_question(
            question="How did that run feel?",
            response="what should I do tomorrow?",
            kind="post_run_feedback",
        )

        self.assertEqual(post_json.call_args.args[1]["model"], "gpt-5.4-mini")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch(
        "running_agent.openai_client._post_json",
        return_value={
            "output_text": (
                '{"answers_question": false, "kind": "post_run_feedback", '
                '"confidence": 0.1, "extracted": {"rpe": 9}}'
            )
        },
    )
    def test_resolve_pending_question_clears_extracted_when_unanswered(self, _post_json) -> None:
        result = resolve_pending_question(
            question="How did that run feel?",
            response="what should I do tomorrow?",
            kind="post_run_feedback",
        )

        self.assertEqual(
            result,
            {
                "answers_question": False,
                "kind": "post_run_feedback",
                "confidence": 0.1,
                "extracted": {},
            },
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch(
        "running_agent.coach_prompt.coach_reflection_context",
        return_value="Current coach thesis",
    )
    @patch(
        "running_agent.coach_prompt.pace_calibration_context",
        return_value="Current VDOT and pace calibration:\nVDOT 50",
    )
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client._post_json", return_value={"output_text": "Reply"})
    def test_coaching_reply_includes_context_and_tools(
        self,
        post_json,
        _athlete_profile_context,
        _pace_calibration_context,
        _coach_reflection_context,
    ) -> None:
        reply = coaching_reply(
            "What should I do today?",
            training_summary="Training summary",
            recent_runs="Recent runs",
            garmin_context="Garmin context",
            weather_context="Weather context",
        )

        self.assertEqual(reply, "Reply")
        payload = post_json.call_args.args[1]
        self.assertIn("Athlete-specific profile:\nProfile note", payload["input"])
        self.assertIn("Current VDOT and pace calibration", payload["input"])
        self.assertIn("Coaching philosophy:", payload["input"])
        self.assertIn("Maintain a working VDOT", payload["input"])
        self.assertIn(
            "Coach's private current training thesis:\nCurrent coach thesis",
            payload["input"],
        )
        self.assertIn("Current training summary:\nTraining summary", payload["input"])
        self.assertIn("Recent runs:\nRecent runs", payload["input"])
        self.assertIn("Garmin readiness context:\nGarmin context", payload["input"])
        self.assertIn("Weather context:\nWeather context", payload["input"])
        tools = {tool["name"]: tool for tool in payload["tools"]}
        self.assertIn("remember_coaching_note", tools)
        self.assertIn("update_training_goal", tools)
        self.assertIn("update_weekly_plan_days", tools)
        self.assertIn("save_weekly_plan", tools)
        self.assertIn("save_race_result", tools)
        self.assertIn("query_local_runs", tools)
        self.assertIn("get_local_run_details", tools)
        self.assertIn("get_garmin_readiness", tools)
        self.assertIn("get_garmin_recovery_trend", tools)
        self.assertIn(
            "shares a day-by-day or week-long schedule",
            tools["save_weekly_plan"]["description"],
        )
        self.assertIn(
            "even if they do not use words like save",
            tools["save_weekly_plan"]["description"],
        )
        self.assertIn(
            "even if they simply write the schedule naturally",
            payload["instructions"],
        )
        self.assertIn("day-by-day lists with workout details", payload["instructions"])
        self.assertIn("update_weekly_plan_days with the changed weekdays", payload["instructions"])
        self.assertIn("quote the returned changed_days or receipt", payload["instructions"])
        self.assertIn("official race result", payload["instructions"])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertNotIn("temperature", payload)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client._post_json", return_value={"output_text": "Reply"})
    def test_coaching_reply_can_disable_tools_without_output_budget(
        self,
        post_json,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "Write a scheduled report.",
            training_summary="Training summary",
            recent_runs="Recent runs",
            weekly_plan="Weekly plan",
            tools_enabled=False,
        )

        self.assertEqual(reply, "Reply")
        payload = post_json.call_args.args[1]
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)
        self.assertNotIn("max_output_tokens", payload)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client._post_json", return_value={"output_text": "Reply"})
    def test_coaching_reply_can_set_output_budget_when_requested(
        self,
        post_json,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "Write a scheduled report.",
            training_summary="Training summary",
            recent_runs="Recent runs",
            max_output_tokens=220,
        )

        self.assertEqual(reply, "Reply")
        payload = post_json.call_args.args[1]
        self.assertEqual(payload["max_output_tokens"], 220)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client._post_json", return_value={"output_text": "Reply"})
    def test_coaching_reply_can_set_temperature(
        self,
        post_json,
        _athlete_profile_context,
    ) -> None:
        coaching_reply(
            "Write a scheduled report.",
            training_summary="Training summary",
            recent_runs="Recent runs",
            temperature=0.1,
        )

        payload = post_json.call_args.args[1]
        self.assertEqual(payload["temperature"], 0.1)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch(
        "running_agent.openai_client._post_json",
        return_value={
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output_text": "Today was planned as rest/cross-training,",
        },
    )
    def test_coaching_reply_rejects_incomplete_response(
        self,
        _post_json,
        _athlete_profile_context,
    ) -> None:
        with self.assertRaisesRegex(RuntimeError, "max_output_tokens"):
            coaching_reply(
                "Write a scheduled report.",
                training_summary="Training summary",
                recent_runs="Recent runs",
            )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch(
        "running_agent.coach_prompt.coach_reflection_context",
        return_value="Current coach thesis",
    )
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client._post_json", return_value={"output_text": "Image reply"})
    def test_image_coaching_reply_includes_text_context_and_image(
        self,
        post_json,
        _athlete_profile_context,
        _coach_reflection_context,
    ) -> None:
        reply = image_coaching_reply(
            "What should I know about this course?",
            image_bytes=b"image bytes",
            mime_type="image/png",
            training_summary="Training summary",
            recent_runs="Recent runs",
            weekly_plan="Weekly plan",
            training_goal="Goal",
        )

        self.assertEqual(reply, "Image reply")
        payload = post_json.call_args.args[1]
        content = payload["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_text")
        self.assertIn("What should I know about this course?", content[0]["text"])
        self.assertIn("Training summary", content[0]["text"])
        self.assertIn("Weekly plan", content[0]["text"])
        self.assertIn("omit UI text, announcement titles", payload["instructions"])
        self.assertIn(
            "locations, reactions, club names, and other source metadata", payload["instructions"]
        )
        self.assertIn("rather than 'Wednesday: Track workout at Underhill", payload["instructions"])
        self.assertEqual(content[1]["type"], "input_image")
        self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))
        tools = {tool["name"] for tool in payload["tools"]}
        self.assertIn("save_weekly_plan", tools)
        self.assertEqual(payload["tool_choice"], "auto")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.save_weekly_plan")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_image",
                "output": [
                    {
                        "type": "function_call",
                        "name": "save_weekly_plan",
                        "call_id": "call_plan",
                        "arguments": '{"plan": "Wednesday 5 x 5 minutes threshold"}',
                    }
                ],
            },
            {"output_text": "I saved that plan update."},
        ],
    )
    def test_image_coaching_reply_executes_plan_tool_and_returns_final_reply(
        self,
        post_json,
        save_weekly_plan,
        _athlete_profile_context,
    ) -> None:
        reply = image_coaching_reply(
            "Update my plan from this screenshot.",
            image_bytes=b"image bytes",
            mime_type="image/jpeg",
            training_summary="Training summary",
            recent_runs="Recent runs",
            weekly_plan="Current plan",
        )

        self.assertEqual(reply, "I saved that plan update.")
        save_weekly_plan.assert_called_once_with(
            "Wednesday 5 x 5 minutes threshold", week_start=None
        )
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(followup_payload["previous_response_id"], "resp_image")
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_plan",
                    "output": (
                        '{"saved": true, "week_start": "", '
                        '"saved_plan": "Wednesday 5 x 5 minutes threshold", '
                        '"receipt": "Saved weekly plan:\\n'
                        'Wednesday 5 x 5 minutes threshold"}'
                    ),
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.save_weekly_plan")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_image",
                "output": [
                    {
                        "type": "function_call",
                        "name": "save_weekly_plan",
                        "call_id": "call_plan",
                        "arguments": (
                            '{"plan": "Monday: 5 easy\\n'
                            "Wednesday: Track workout for 6/10 at Underhill Sports Complex: "
                            "structured warmup; 5 x 5 min @ threshold; 2 min recovery\\n"
                            'Saturday: 12 long"}'
                        ),
                    }
                ],
            },
            {"output_text": "I saved that plan update."},
        ],
    )
    def test_image_plan_tool_strips_announcement_metadata(
        self,
        _post_json,
        save_weekly_plan,
        _athlete_profile_context,
    ) -> None:
        image_coaching_reply(
            "Update my plan from this screenshot.",
            image_bytes=b"image bytes",
            mime_type="image/jpeg",
            training_summary="Training summary",
            recent_runs="Recent runs",
            weekly_plan="Current plan",
        )

        save_weekly_plan.assert_called_once_with(
            "Monday: 5 easy\n"
            "Wednesday: structured warmup; 5 x 5 min @ threshold; 2 min recovery\n"
            "Saturday: 12 long",
            week_start=None,
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.save_weekly_plan")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_image",
                "output": [
                    {
                        "type": "function_call",
                        "name": "save_weekly_plan",
                        "call_id": "call_plan",
                        "arguments": (
                            '{"plan": "Monday: 5 easy\\n'
                            "Wednesday: 4 easy + track workout: 5 x 5 min @ threshold, "
                            '2 min recovery\\nSaturday: 12 long"}'
                        ),
                    }
                ],
            },
            {"output_text": "I saved that plan update."},
        ],
    )
    def test_image_plan_tool_replaces_old_workout_before_track_workout(
        self,
        _post_json,
        save_weekly_plan,
        _athlete_profile_context,
    ) -> None:
        image_coaching_reply(
            "Update my plan from this screenshot.",
            image_bytes=b"image bytes",
            mime_type="image/jpeg",
            training_summary="Training summary",
            recent_runs="Recent runs",
            weekly_plan="Current plan",
        )

        save_weekly_plan.assert_called_once_with(
            "Monday: 5 easy\n"
            "Wednesday: 5 x 5 min @ threshold, 2 min recovery\n"
            "Saturday: 12 long",
            week_start=None,
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.update_weekly_plan_days")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_plan",
                "output": [
                    {
                        "type": "function_call",
                        "name": "update_weekly_plan_days",
                        "call_id": "call_plan",
                        "arguments": (
                            '{"updates": ['
                            '{"day": "Saturday", "workout": "rest"}, '
                            '{"day": "Sunday", "workout": "10 miles"}'
                            "]}"
                        ),
                    }
                ],
            },
            {"output_text": "I moved the long run."},
        ],
    )
    def test_coaching_reply_executes_weekly_plan_day_update_tool(
        self,
        post_json,
        update_weekly_plan_days,
        _athlete_profile_context,
    ) -> None:
        update_weekly_plan_days.return_value = {"text": "Saturday rest\nSunday 10 miles"}

        reply = coaching_reply(
            "Move today's run to tomorrow in the plan.",
            training_summary="Training summary",
            recent_runs="Recent runs",
            weekly_plan="Saturday 10 miles",
        )

        self.assertEqual(reply, "I moved the long run.")
        update_weekly_plan_days.assert_called_once_with({"Saturday": "rest", "Sunday": "10 miles"})
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_plan",
                    "output": (
                        '{"saved": true, '
                        '"changed_days": ["Saturday rest", "Sunday 10 miles"], '
                        '"saved_plan": "Saturday rest\\nSunday 10 miles", '
                        '"receipt": "Saved plan changes: Saturday rest; Sunday 10 miles"}'
                    ),
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.append_coaching_preference")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "remember_coaching_note",
                        "call_id": "call_1",
                        "arguments": '{"note": "Prefers long runs on Saturday."}',
                    }
                ],
            },
            {"output_text": "Got it. I will keep that in mind."},
        ],
    )
    def test_coaching_reply_executes_memory_tool_and_returns_final_reply(
        self,
        post_json,
        append_coaching_preference,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "Remember that I prefer long runs on Saturday.",
            training_summary="Training summary",
            recent_runs="Recent runs",
        )

        self.assertEqual(reply, "Got it. I will keep that in mind.")
        append_coaching_preference.assert_called_once_with("Prefers long runs on Saturday.")
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(followup_payload["previous_response_id"], "resp_1")
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": '{"saved": true}',
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch(
        "running_agent.openai_client.get_local_run_details",
        return_value="Lap 1: 0.25 mi at 5:50/mi",
    )
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "get_local_run_details",
                        "call_id": "call_detail",
                        "arguments": (
                            '{"selector": "latest_run", "activity_id": "", "query": "", '
                            '"date": "", "days": 365}'
                        ),
                    }
                ],
            },
            {"output_text": "Your 4x20s were right around 5:50 pace."},
        ],
    )
    def test_coaching_reply_executes_local_run_details_tool_and_returns_final_reply(
        self,
        post_json,
        get_local_run_details,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "What were my splits for the 4x20s portion of my last run?",
            training_summary="Training summary",
            recent_runs="Recent runs",
        )

        self.assertEqual(reply, "Your 4x20s were right around 5:50 pace.")
        get_local_run_details.assert_called_once_with(
            selector="latest_run", activity_id="", query="", date="", days=365
        )
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(followup_payload["previous_response_id"], "resp_1")
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_detail",
                    "output": '{"result": "Lap 1: 0.25 mi at 5:50/mi"}',
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.query_local_runs", return_value="Race: 6.20 mi")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "query_local_runs",
                        "call_id": "call_strava",
                        "arguments": ('{"query": "", "days": 365, "limit": 3, "races_only": true}'),
                    }
                ],
            },
            {"output_text": "Your last race was 6.2 miles."},
        ],
    )
    def test_coaching_reply_executes_strava_query_tool_and_returns_final_reply(
        self,
        post_json,
        query_local_runs,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "What distance was my last race?",
            training_summary="Training summary",
            recent_runs="Recent runs",
        )

        self.assertEqual(reply, "Your last race was 6.2 miles.")
        query_local_runs.assert_called_once_with(query="", days=365, limit=3, races_only=True)
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(followup_payload["previous_response_id"], "resp_1")
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_strava",
                    "output": '{"result": "Race: 6.20 mi"}',
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.save_race_result")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "save_race_result",
                        "call_id": "call_race",
                        "arguments": (
                            '{"race_name": "North Jersey Pride Run", '
                            '"race_date": "2026-06-07", "distance": "5K", '
                            '"time": "19:59", "source": "athlete"}'
                        ),
                    }
                ],
            },
            {"output_text": "I saved the official 5K result."},
        ],
    )
    def test_coaching_reply_executes_save_race_result_tool(
        self,
        post_json,
        save_race_result,
        _athlete_profile_context,
    ) -> None:
        save_race_result.return_value = {"race_name": "North Jersey Pride Run"}

        reply = coaching_reply(
            "Actually my official 5K time was 19:59.",
            training_summary="Training summary",
            recent_runs="Recent runs",
        )

        self.assertEqual(reply, "I saved the official 5K result.")
        save_race_result.assert_called_once_with(
            race_name="North Jersey Pride Run",
            race_date="2026-06-07",
            distance="5K",
            time="19:59",
            source="athlete",
        )
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_race",
                    "output": '{"saved": true, "result": {"race_name": "North Jersey Pride Run"}}',
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.daily_checkin.current_garmin_context", return_value="Readiness: 52")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "get_garmin_readiness",
                        "call_id": "call_garmin",
                        "arguments": "{}",
                    }
                ],
            },
            {"output_text": "Readiness is moderate today."},
        ],
    )
    def test_coaching_reply_executes_garmin_readiness_tool_and_returns_final_reply(
        self,
        post_json,
        current_garmin_context,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "How is my Garmin readiness today?",
            training_summary="Training summary",
            recent_runs="Recent runs",
        )

        self.assertEqual(reply, "Readiness is moderate today.")
        current_garmin_context.assert_called_once_with()
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_garmin",
                    "output": '{"result": "Readiness: 52"}',
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.safe_garmin_weekly_context", return_value="7-day trend")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "get_garmin_recovery_trend",
                        "call_id": "call_garmin_week",
                        "arguments": '{"days": 7}',
                    }
                ],
            },
            {"output_text": "Recovery is stable this week."},
        ],
    )
    def test_coaching_reply_executes_garmin_trend_tool_and_returns_final_reply(
        self,
        post_json,
        safe_garmin_weekly_context,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "How has my HRV trended this week?",
            training_summary="Training summary",
            recent_runs="Recent runs",
        )

        self.assertEqual(reply, "Recovery is stable this week.")
        safe_garmin_weekly_context.assert_called_once_with(days=7)
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_garmin_week",
                    "output": '{"result": "7-day trend"}',
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.save_weekly_plan")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "save_weekly_plan",
                        "call_id": "call_plan",
                        "arguments": (
                            '{"plan": "Monday 5 easy\\nWednesday 2mi WU, 6x400m, CD\\n'
                            'Saturday 10 easy"}'
                        ),
                    }
                ],
            },
            {"output_text": "Got it. I saved that plan."},
        ],
    )
    def test_coaching_reply_executes_plan_tool_and_returns_final_reply(
        self,
        post_json,
        save_weekly_plan,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "Here is my plan for next week: Monday 5 easy, Wednesday 6x400, Saturday 10.",
            training_summary="Training summary",
            recent_runs="Recent runs",
            weekly_plan="Current plan",
        )

        self.assertEqual(reply, "Got it. I saved that plan.")
        save_weekly_plan.assert_called_once_with(
            "Monday 5 easy\nWednesday 2mi WU, 6x400m, CD\nSaturday 10 easy",
            week_start=None,
        )
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(followup_payload["previous_response_id"], "resp_1")
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_plan",
                    "output": (
                        '{"saved": true, "week_start": "", '
                        '"saved_plan": "Monday 5 easy\\n'
                        'Wednesday 2mi WU, 6x400m, CD\\nSaturday 10 easy", '
                        '"receipt": "Saved weekly plan:\\nMonday 5 easy\\n'
                        'Wednesday 2mi WU, 6x400m, CD\\nSaturday 10 easy"}'
                    ),
                }
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.coach_prompt.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client.save_training_goal")
    @patch(
        "running_agent.openai_client._post_json",
        side_effect=[
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "update_training_goal",
                        "call_id": "call_goal",
                        "arguments": (
                            '{"goal": "Run the Boston Marathon on October 12 with a target '
                            'of 3:10 while staying healthy."}'
                        ),
                    }
                ],
            },
            {"output_text": "Got it. I updated that goal."},
        ],
    )
    def test_coaching_reply_executes_goal_tool_and_returns_final_reply(
        self,
        post_json,
        save_training_goal,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "My main goal is Boston on Oct 12, ideally 3:10.",
            training_summary="Training summary",
            recent_runs="Recent runs",
            training_goal="Current goal: stay healthy.",
        )

        self.assertEqual(reply, "Got it. I updated that goal.")
        save_training_goal.assert_called_once_with(
            "Run the Boston Marathon on October 12 with a target of 3:10 while staying healthy."
        )
        self.assertEqual(post_json.call_count, 2)
        followup_payload = post_json.call_args_list[1].args[1]
        self.assertEqual(followup_payload["previous_response_id"], "resp_1")
        self.assertEqual(
            followup_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_goal",
                    "output": '{"saved": true}',
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
