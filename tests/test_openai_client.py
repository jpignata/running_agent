from __future__ import annotations

import unittest
from unittest.mock import patch

from running_agent.openai_client import coaching_reply


class OpenAIClientTest(unittest.TestCase):
    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.openai_client.athlete_profile_context", return_value="Profile note")
    @patch("running_agent.openai_client._post_json", return_value={"output_text": "Reply"})
    def test_coaching_reply_includes_profile_and_garmin_rubric(
        self,
        post_json,
        _athlete_profile_context,
    ) -> None:
        reply = coaching_reply(
            "What should I do today?",
            training_summary="Training summary",
            recent_runs="Recent runs",
            garmin_context="Garmin context",
        )

        self.assertEqual(reply, "Reply")
        payload = post_json.call_args.args[1]
        self.assertIn("Athlete-specific profile:\nProfile note", payload["input"])
        self.assertIn("Garmin coaching rubric:", payload["input"])
        self.assertIn("Training progression rubric:", payload["input"])
        self.assertIn("weekly volume increases usually around 5-10%", payload["input"])
        self.assertIn("Do not recommend downgrading", payload["input"])
        self.assertIn("appropriately challenging training", payload["instructions"])
        self.assertIn("do not let one generic Garmin label override", payload["instructions"])
        self.assertIn("durable coaching preference", payload["instructions"])
        self.assertIn("I generally", payload["instructions"])
        self.assertIn("briefly acknowledge", payload["instructions"])
        self.assertIn(
            "quality sessions on Wednesdays or long runs on Saturdays",
            payload["tools"][0]["description"],
        )
        self.assertEqual(payload["tools"][0]["name"], "remember_coaching_note")
        self.assertEqual(payload["tool_choice"], "auto")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch("running_agent.openai_client.athlete_profile_context", return_value="Profile note")
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


if __name__ == "__main__":
    unittest.main()
