from __future__ import annotations

import unittest
from unittest.mock import patch

from running_agent import openai_client
from running_agent.eval_runner import format_eval_results, load_case, run_behavioral_case


class EvalRunnerTest(unittest.TestCase):
    def test_plan_adjustment_eval_passes_when_model_saves_revised_complete_plan(self) -> None:
        case = load_case_path()

        def fake_reply(*_args, **_kwargs) -> str:
            openai_client.save_weekly_plan(
                "\n".join(
                    [
                        "Monday: 5 easy",
                        "Tuesday: 5 easy",
                        "Wednesday: 5 recovery",
                        "Thursday: 8 with 4x1200m",
                        "Friday: rest",
                        "Saturday: 14 long",
                        "Sunday: 4 recovery",
                    ]
                )
            )
            return "Got it, I updated the week."

        result = run_behavioral_case(case, reply_func=fake_reply)

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertEqual(len(result.saved_plans), 1)

    def test_plan_adjustment_eval_fails_when_model_does_not_save_plan(self) -> None:
        result = run_behavioral_case(load_case_path(), reply_func=lambda *_args, **_kwargs: "OK")

        self.assertFalse(result.passed)
        self.assertIn("expected exactly one save_weekly_plan call", result.checks[0].message)

    @patch("running_agent.eval_runner.openai_client.image_coaching_reply")
    def test_image_plan_eval_uses_image_reply_path(self, image_coaching_reply) -> None:
        def fake_image_reply(*_args, **_kwargs) -> str:
            openai_client.save_weekly_plan(
                "\n".join(
                    [
                        "Monday: 5 easy",
                        "Tuesday: 4 easy",
                        "Wednesday: 5 x 5 minutes at threshold",
                        "Thursday: 7 easy",
                        "Friday: rest",
                        "Saturday: 12 long",
                        "Sunday: 4 recovery",
                    ]
                )
            )
            return "Saved from image."

        image_coaching_reply.side_effect = fake_image_reply

        result = run_behavioral_case(load_case_path("image_plan_update_from_screenshot.json"))

        self.assertTrue(result.passed, format_eval_results([result]))
        image_coaching_reply.assert_called_once()
        self.assertGreater(len(image_coaching_reply.call_args.kwargs["image_bytes"]), 0)
        self.assertEqual(image_coaching_reply.call_args.kwargs["mime_type"], "image/jpeg")


def load_case_path(filename: str = "adjust_existing_weekly_plan.json"):
    from running_agent.eval_runner import CASE_DIR

    return load_case(CASE_DIR / filename)


if __name__ == "__main__":
    unittest.main()
