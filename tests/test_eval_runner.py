from __future__ import annotations

import unittest
from unittest.mock import patch

from running_agent import coach_prompt, openai_client
from running_agent.eval_runner import (
    EvalCheck,
    EvalResult,
    eval_temperature,
    format_eval_results,
    judge_reply,
    load_case,
    run_case,
    run_evals,
    run_judge_model,
)


class EvalRunnerTest(unittest.TestCase):
    def test_load_case_uses_filename_stem_as_name(self) -> None:
        case = load_case_path("recall_last_race.json")

        self.assertEqual(case["name"], "recall_last_race")
        self.assertIn("local Strava retrieval", case["description"])

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

        result = run_case(case, reply_func=fake_reply)

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertEqual(len(result.saved_plans), 1)

    def test_plan_adjustment_eval_fails_when_model_does_not_save_plan(self) -> None:
        result = run_case(load_case_path(), reply_func=lambda *_args, **_kwargs: "OK")

        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "expected exactly one save_weekly_plan call" in check.message
                for check in result.checks
            )
        )

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

        result = run_case(load_case_path("image_plan_update_from_screenshot.json"))

        self.assertTrue(result.passed, format_eval_results([result]))
        image_coaching_reply.assert_called_once()
        self.assertGreater(len(image_coaching_reply.call_args.kwargs["image_bytes"]), 0)
        self.assertEqual(image_coaching_reply.call_args.kwargs["mime_type"], "image/jpeg")
        self.assertEqual(image_coaching_reply.call_args.kwargs["temperature"], 0.1)

    def test_retrieval_eval_passes_when_model_queries_races(self) -> None:
        seen_kwargs = {}

        def fake_reply(*_args, **_kwargs) -> str:
            seen_kwargs.update(_kwargs)
            result = openai_client.query_local_runs(
                query="last race",
                days=365,
                limit=3,
                races_only=True,
            )
            self.assertIn("Riverfront 5K", result)
            return "Your last race was Riverfront 5K at 6:21/mi."

        result = run_case(
            load_case_path("recall_last_race.json"),
            reply_func=fake_reply,
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertEqual(result.tool_calls[0]["name"], "query_local_runs")
        self.assertTrue(result.tool_calls[0]["arguments"]["races_only"])
        self.assertEqual(seen_kwargs["temperature"], 0.1)

    def test_retrieval_eval_fails_without_lookup(self) -> None:
        result = run_case(
            load_case_path("recall_last_race.json"),
            reply_func=lambda *_args, **_kwargs: "I think it was around 6:00 pace.",
        )

        self.assertFalse(result.passed)
        self.assertIn("expected query_local_runs to be called", result.checks[0].message)

    @patch("running_agent.eval_runner.openai_client.coaching_reply")
    def test_run_case_can_pin_current_date(self, coaching_reply) -> None:
        original_coach_now = coach_prompt.coach_now

        def fake_coaching_reply(*_args, **_kwargs) -> str:
            self.assertEqual(coach_prompt.coach_now().date().isoformat(), "2026-06-09")
            return "Pinned date reply."

        coaching_reply.side_effect = fake_coaching_reply

        result = run_case(
            {
                "name": "pinned_date",
                "current_date": "2026-06-09",
                "user_message": "What is tomorrow?",
            }
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertIs(coach_prompt.coach_now, original_coach_now)

    def test_tool_call_not_called_eval_passes_when_tool_is_not_called(self) -> None:
        result = run_case(
            {
                "name": "hypothetical_plan",
                "user_message": "What might next week look like?",
                "expected": {
                    "tool_calls": {
                        "not_called": ["save_weekly_plan"],
                    }
                },
            },
            reply_func=lambda *_args, **_kwargs: "Next week could stay mostly easy.",
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertTrue(
            any(
                "expected save_weekly_plan not to be called" in check.message
                for check in result.checks
            )
        )

    def test_tool_call_not_called_eval_fails_when_tool_is_called(self) -> None:
        def fake_reply(*_args, **_kwargs) -> str:
            openai_client.save_weekly_plan("Monday: 5 easy")
            return "I saved that as next week."

        result = run_case(
            {
                "name": "hypothetical_plan",
                "user_message": "What might next week look like?",
                "expected": {
                    "tool_calls": {
                        "not_called": ["save_weekly_plan"],
                    }
                },
            },
            reply_func=fake_reply,
        )

        self.assertFalse(result.passed)
        self.assertIn("expected save_weekly_plan not to be called", result.checks[0].message)

    def test_judged_reply_eval_passes_with_fake_judge(self) -> None:
        def fake_judge(_case, _reply):
            return {"passed": True, "rationale": "Safe and specific.", "failures": []}

        result = run_case(
            load_case_path("judged_soreness_long_run.json"),
            reply_func=lambda *_args, **_kwargs: (
                "Treat the Achilles as the limiter. If it is sore tomorrow, skip the "
                "12 and do easy cross-training or a short easy run only if the warmup "
                "is pain-free."
            ),
            judge_func=fake_judge,
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertTrue(any("judge passed" in check.message for check in result.checks))
        self.assertIn("Safe and specific.", format_eval_results([result]))

    def test_judged_reply_eval_fails_when_fake_judge_finds_unmet_criteria(self) -> None:
        result = run_case(
            load_case_path("judged_soreness_long_run.json"),
            reply_func=lambda *_args, **_kwargs: "Your Achilles is fine. Do the 12.",
            judge_func=lambda _case, _reply: {
                "passed": False,
                "rationale": "Too risky.",
                "failures": ["Does not prioritize Achilles injury risk."],
            },
        )

        self.assertFalse(result.passed)
        self.assertTrue(any("judge failed" in check.message for check in result.checks))
        self.assertTrue(
            any(
                "Does not prioritize Achilles injury risk." in check.message
                for check in result.checks
            )
        )

    def test_judge_reply_requires_explicit_passed_true(self) -> None:
        checks = judge_reply(
            {"judge": {}},
            "Reply",
            judge_func=lambda _case, _reply: {"rationale": "Missing decision criteria."},
        )

        self.assertFalse(checks[0].passed)
        self.assertIn("judge failed", checks[0].message)

    def test_case_runs_expected_rules_and_judge_when_both_keys_are_present(self) -> None:
        result = run_case(
            {
                "name": "mixed_case",
                "user_message": "What should I do?",
                "expected": {"reply_must_include": ["Achilles"]},
                "judge": {"criteria": ["Safe advice"], "pass_condition": "Pass if safe."},
            },
            reply_func=lambda *_args, **_kwargs: "Protect the Achilles.",
            judge_func=lambda _case, _reply: {
                "passed": True,
                "rationale": "Safe.",
                "failures": [],
            },
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertTrue(
            any("reply includes 'Achilles'" in check.message for check in result.checks)
        )
        self.assertTrue(any("judge passed" in check.message for check in result.checks))

    def test_rule_eval_checks_reply_format_invariants(self) -> None:
        result = run_case(
            {
                "name": "format_case",
                "user_message": "Quick read?",
                "expected": {
                    "reply_max_chars": 50,
                    "reply_must_not_include": ["**"],
                    "reply_must_not_match": ["^\\s*[-*]\\s"],
                },
            },
            reply_func=lambda *_args, **_kwargs: "Keep it easy tomorrow.",
        )

        self.assertTrue(result.passed, format_eval_results([result]))
        self.assertTrue(any("reply length <= 50" in check.message for check in result.checks))

    def test_rule_eval_fails_on_forbidden_formatting(self) -> None:
        result = run_case(
            {
                "name": "format_case",
                "user_message": "Quick read?",
                "expected": {
                    "reply_max_chars": 50,
                    "reply_must_not_include": ["**"],
                    "reply_must_not_match": ["^\\s*[-*]\\s", "(^|\\s)_[^_\\n]+_(\\s|$)"],
                },
            },
            reply_func=lambda *_args, **_kwargs: "- **Easy** tomorrow, _no workout_.",
        )

        self.assertFalse(result.passed)
        self.assertTrue(
            any("reply does not include '**'" in check.message for check in result.checks)
        )
        self.assertTrue(any("reply does not match" in check.message for check in result.checks))

    @patch.dict("os.environ", {"OPENAI_EVAL_TEMPERATURE": "0.2"}, clear=True)
    def test_eval_temperature_uses_environment_override(self) -> None:
        self.assertEqual(eval_temperature(), 0.2)

    @patch.dict("os.environ", {"OPENAI_EVAL_TEMPERATURE": "warm"}, clear=True)
    def test_eval_temperature_rejects_invalid_override(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "OPENAI_EVAL_TEMPERATURE"):
            eval_temperature()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "key"}, clear=True)
    @patch(
        "running_agent.eval_runner.openai_client._post_json",
        return_value={"output_text": '{"passed": true, "rationale": "OK.", "failures": []}'},
    )
    def test_run_judge_model_sets_eval_temperature(self, post_json) -> None:
        run_judge_model(
            {
                "name": "case",
                "user_message": "Question",
                "judge": {"criteria": ["Do the thing"], "pass_condition": "Pass if done."},
            },
            "Reply",
        )

        payload = post_json.call_args.args[1]
        self.assertEqual(payload["temperature"], 0.1)
        self.assertEqual(payload["input"][0]["role"], "user")

    def test_format_eval_results_omits_debug_details_by_default(self) -> None:
        text = format_eval_results([sample_result()])

        self.assertIn("PASS sample_case", text)
        self.assertIn("PASS check passed", text)
        self.assertIn("\n\nSummary: 1 passed, 0 failed", text)
        self.assertIn("Summary: 1 passed, 0 failed", text)
        self.assertNotIn("Saved plan:", text)
        self.assertNotIn("Tool calls:", text)
        self.assertNotIn("Reply:", text)

    def test_format_eval_results_includes_debug_details_when_requested(self) -> None:
        text = format_eval_results([sample_result()], debug=True)

        self.assertIn("Saved plan:", text)
        self.assertIn("Monday: 5 easy", text)
        self.assertIn("Tool calls:", text)
        self.assertIn('"name": "query_local_runs"', text)
        self.assertIn("Reply:", text)
        self.assertIn("Model reply", text)
        self.assertIn("Summary: 1 passed, 0 failed", text)

    def test_format_eval_results_summarizes_failures(self) -> None:
        text = format_eval_results(
            [sample_result(), sample_result(name="failing_case", passed=False)]
        )

        self.assertIn("PASS sample_case", text)
        self.assertIn("FAIL failing_case", text)
        self.assertIn("Summary: 1 passed, 1 failed", text)

    @patch("running_agent.eval_runner.run_case")
    def test_run_evals_without_case_runs_all_cases(self, run_case_) -> None:
        run_case_.side_effect = lambda case: case["name"]

        results = run_evals()

        self.assertIn("adjust_existing_weekly_plan", results)
        self.assertIn("hypothetical_plan_no_save", results)
        self.assertIn("image_plan_update_from_screenshot", results)
        self.assertIn("judged_soreness_long_run", results)
        self.assertIn("plain_text_reply_format", results)
        self.assertIn("recall_last_race", results)


def load_case_path(filename: str = "adjust_existing_weekly_plan.json"):
    from running_agent.eval_runner import CASE_DIR

    return load_case(CASE_DIR / filename)


def sample_result(name: str = "sample_case", passed: bool = True) -> EvalResult:
    return EvalResult(
        name=name,
        passed=passed,
        reply="Model reply",
        saved_plans=["Monday: 5 easy"],
        tool_calls=[{"name": "query_local_runs", "arguments": {"races_only": True}}],
        checks=[EvalCheck(True, "check passed")],
    )


if __name__ == "__main__":
    unittest.main()
