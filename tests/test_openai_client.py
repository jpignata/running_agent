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


if __name__ == "__main__":
    unittest.main()
