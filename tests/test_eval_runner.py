from __future__ import annotations

import unittest
from unittest.mock import patch

from running_agent import openai_client
from running_agent.eval_runner import (
    format_eval_results,
    judge_reply,
    load_case,
    run_behavioral_case,
    run_evals,
)


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

    def test_retrieval_eval_passes_when_model_queries_races(self) -> None:
        def fake_reply(*_args, **_kwargs) -> str:
            result = openai_client.query_local_runs(
                query="last race",
                days=365,
                limit=3,
                races_only=True,
            )
            self.assertIn("Riverfront 5K", result)
            return "Your last race was Riverfront 5K at 6:21/mi."

        result = run_behavioral_case(
            load_case_path("recall_last_race.json"),
            reply_func=fake_reply,
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertEqual(result.tool_calls[0]["name"], "query_local_runs")
        self.assertTrue(result.tool_calls[0]["arguments"]["races_only"])

    def test_retrieval_eval_fails_without_lookup(self) -> None:
        result = run_behavioral_case(
            load_case_path("recall_last_race.json"),
            reply_func=lambda *_args, **_kwargs: "I think it was around 6:00 pace.",
        )

        self.assertFalse(result.passed)
        self.assertIn("expected query_local_runs call", result.checks[0].message)

    def test_judged_reply_eval_passes_with_fake_judge(self) -> None:
        def fake_judge(_case, _reply):
            return {"passed": True, "rationale": "Safe and specific.", "failures": []}

        result = run_behavioral_case(
            load_case_path("judged_soreness_long_run.json"),
            reply_func=lambda *_args, **_kwargs: (
                "Treat the Achilles as the limiter. If it is sore tomorrow, skip the "
                "12 and do easy cross-training or a short easy run only if the warmup "
                "is pain-free."
            ),
            judge_func=fake_judge,
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertIn("judge passed", result.checks[-1].message)

    def test_judged_reply_eval_fails_when_fake_judge_finds_unmet_criteria(self) -> None:
        result = run_behavioral_case(
            load_case_path("judged_soreness_long_run.json"),
            reply_func=lambda *_args, **_kwargs: "Your Achilles is fine. Do the 12.",
            judge_func=lambda _case, _reply: {
                "passed": False,
                "rationale": "Too risky.",
                "failures": ["Does not prioritize Achilles injury risk."],
            },
        )

        self.assertFalse(result.passed)
        self.assertIn("judge failed", result.checks[-1].message)
        self.assertIn("Does not prioritize Achilles injury risk.", result.checks[-1].message)

    def test_judge_reply_requires_explicit_passed_true(self) -> None:
        checks = judge_reply(
            {"judge": {}},
            "Reply",
            judge_func=lambda _case, _reply: {"rationale": "Missing decision criteria."},
        )

        self.assertFalse(checks[0].passed)
        self.assertIn("judge failed", checks[0].message)

    @patch("running_agent.eval_runner.run_behavioral_case")
    def test_run_evals_without_case_runs_all_cases(self, run_behavioral_case_) -> None:
        run_behavioral_case_.side_effect = lambda case: case["name"]

        results = run_evals()

        self.assertIn("adjust_existing_weekly_plan_move_workout", results)
        self.assertIn("image_plan_update_from_screenshot", results)
        self.assertIn("judged_soreness_long_run_advice", results)
        self.assertIn("recall_last_race_uses_local_retrieval", results)


def load_case_path(filename: str = "adjust_existing_weekly_plan.json"):
    from running_agent.eval_runner import CASE_DIR

    return load_case(CASE_DIR / filename)


if __name__ == "__main__":
    unittest.main()
