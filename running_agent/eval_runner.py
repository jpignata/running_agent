from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import coach_agent as coach_agent_module
from . import coach_prompt, openai_client
from .auth import load_env_file
from .coach_time import COACH_TIME_ZONE
from .plan_store import parse_weekly_plan

CASE_DIR = Path(__file__).resolve().parent.parent / "evals" / "cases"
DEFAULT_JUDGE_MODEL = "gpt-5.5"
DEFAULT_EVAL_TEMPERATURE = 0.1


@dataclass(frozen=True)
class EvalCheck:
    passed: bool
    message: str


@dataclass(frozen=True)
class EvalResult:
    name: str
    passed: bool
    reply: str
    saved_plans: list[str]
    tool_calls: list[dict[str, Any]]
    checks: list[EvalCheck]
    saved_feedback: list[dict[str, Any]] = field(default_factory=list)


ReplyFunc = Callable[..., str]
JudgeFunc = Callable[[dict[str, Any], str], dict[str, Any]]


def run_evals(case_name: str | None = None) -> list[EvalResult]:
    case_paths = [_case_path(case_name)] if case_name else _all_case_paths()
    return [run_case(load_case(path)) for path in case_paths]


def load_case(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Eval case must be a JSON object: {path}")
    data = dict(data)
    data["name"] = path.stem
    return data


def run_case(
    case: dict[str, Any],
    reply_func: ReplyFunc | None = None,
    judge_func: JudgeFunc | None = None,
) -> EvalResult:
    if case.get("interaction") == "coach_agent":
        return run_coach_agent_case(case, reply_func=reply_func)

    saved_plans: list[str] = []
    saved_goals: list[str] = []
    saved_race_results: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    original_save_weekly_plan = openai_client.save_weekly_plan
    original_update_weekly_plan_days = openai_client.update_weekly_plan_days
    original_save_training_goal = openai_client.save_training_goal
    original_save_race_result = openai_client.save_race_result
    original_query_local_runs = openai_client.query_local_runs
    original_get_local_run_details = openai_client.get_local_run_details
    original_coach_now = coach_prompt.coach_now
    original_pace_calibration_context = coach_prompt.pace_calibration_context
    original_coach_reflection_context = coach_prompt.coach_reflection_context
    original_race_results_context = coach_prompt.race_results_context

    def capture_save_weekly_plan(plan_text: str):
        saved_plans.append(plan_text)
        tool_calls.append({"name": "save_weekly_plan", "arguments": {"plan": plan_text}})
        return {"text": plan_text}

    def capture_update_weekly_plan_days(updates: dict[str, str]):
        current = parse_weekly_plan(context.get("weekly_plan", ""))
        current.update(updates)
        plan_text = "\n".join(
            f"{day} {current[day]}"
            for day in (
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            )
            if day in current
        )
        saved_plans.append(plan_text)
        tool_calls.append({"name": "update_weekly_plan_days", "arguments": {"updates": updates}})
        return {"text": plan_text}

    def capture_save_training_goal(goal_text: str):
        saved_goals.append(goal_text)
        tool_calls.append({"name": "update_training_goal", "arguments": {"goal": goal_text}})
        return {"text": goal_text}

    def capture_save_race_result(**kwargs):
        result = dict(kwargs)
        saved_race_results.append(result)
        tool_calls.append({"name": "save_race_result", "arguments": result})
        return result

    def capture_query_local_runs(**kwargs):
        tool_calls.append({"name": "query_local_runs", "arguments": dict(kwargs)})
        return _tool_result(case, "query_local_runs")

    def capture_get_local_run_details(**kwargs):
        tool_calls.append({"name": "get_local_run_details", "arguments": dict(kwargs)})
        return _tool_result(case, "get_local_run_details")

    openai_client.save_weekly_plan = capture_save_weekly_plan
    openai_client.update_weekly_plan_days = capture_update_weekly_plan_days
    openai_client.save_training_goal = capture_save_training_goal
    openai_client.save_race_result = capture_save_race_result
    openai_client.query_local_runs = capture_query_local_runs
    openai_client.get_local_run_details = capture_get_local_run_details
    context = case.get("initial_context") or {}
    coach_prompt.pace_calibration_context = lambda: context.get(
        "pace_calibration",
        "No pace calibration has been saved yet.",
    )
    coach_prompt.coach_reflection_context = lambda: context.get(
        "coach_reflection",
        "No coach reflection has been recorded yet.",
    )
    coach_prompt.race_results_context = lambda: context.get(
        "race_results",
        "No official race results have been saved yet.",
    )
    if case.get("current_date"):
        pinned_now = datetime.fromisoformat(str(case["current_date"])).replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=COACH_TIME_ZONE,
        )
        coach_prompt.coach_now = lambda: pinned_now
    try:
        reply = _run_case_model_call(case, context, reply_func)
    finally:
        openai_client.save_weekly_plan = original_save_weekly_plan
        openai_client.update_weekly_plan_days = original_update_weekly_plan_days
        openai_client.save_training_goal = original_save_training_goal
        openai_client.save_race_result = original_save_race_result
        openai_client.query_local_runs = original_query_local_runs
        openai_client.get_local_run_details = original_get_local_run_details
        coach_prompt.coach_now = original_coach_now
        coach_prompt.pace_calibration_context = original_pace_calibration_context
        coach_prompt.coach_reflection_context = original_coach_reflection_context
        coach_prompt.race_results_context = original_race_results_context

    checks = score_case(case, saved_plans, saved_goals, tool_calls, reply, judge_func=judge_func)
    return EvalResult(
        name=str(case.get("name") or "unnamed"),
        passed=all(check.passed for check in checks),
        reply=reply,
        saved_plans=saved_plans,
        tool_calls=tool_calls,
        checks=checks,
    )


def run_coach_agent_case(
    case: dict[str, Any],
    reply_func: ReplyFunc | None = None,
) -> EvalResult:
    saved_feedback: list[dict[str, Any]] = []
    replies: list[str] = []
    state = dict(case.get("initial_state") or {})
    original_append_post_run_feedback = coach_agent_module.append_post_run_feedback
    original_append_run_result = coach_agent_module.append_run_result
    original_coaching_reply = coach_agent_module.coaching_reply
    original_current_garmin_context = coach_agent_module.current_garmin_context
    original_normalize_post_run_feedback = coach_agent_module.normalize_post_run_feedback
    original_resolve_pending_question = coach_agent_module.resolve_pending_question
    original_save_synced_run_detail = coach_agent_module.save_synced_run_detail
    normalizations = {
        str(turn.get("user_message")): dict(turn.get("normalized_feedback") or {})
        for turn in case.get("turns") or []
        if "user_message" in turn
    }

    def capture_post_run_feedback(
        text: str,
        *,
        normalized: dict[str, Any] | None = None,
        activity_id: Any = None,
        run_date: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalized or normalizations.get(text) or {}
        entry = {
            "type": "post_run_feedback",
            "activity_id": activity_id,
            "run_date": run_date,
            "raw": text.strip(),
            **{
                key: value
                for key, value in (normalizations.get(text) or {}).items()
                if key != "is_feedback" and value is not None
            },
        }
        saved_feedback.append(entry)
        return entry

    def fake_normalize_post_run_feedback(text: str) -> dict[str, Any]:
        return normalizations.get(
            text,
            {"is_feedback": False, "rpe": None, "legs": None, "pain": None, "notes": None},
        )

    def fake_resolve_pending_question(
        *,
        question: str,
        response: str,
        kind: str,
    ) -> dict[str, Any]:
        normalized = normalizations.get(response) or {}
        is_answer = bool(normalized.get("is_feedback"))
        return {
            "answers_question": is_answer,
            "kind": kind,
            "confidence": 1.0 if is_answer else 0.0,
            "extracted": normalized if is_answer else {},
        }

    def fake_coaching_reply(*args, **kwargs) -> str:
        if reply_func:
            return reply_func(*args, **kwargs)
        return str(case.get("model_reply") or "Nice work on that run.")

    coach_agent_module.append_post_run_feedback = capture_post_run_feedback
    coach_agent_module.append_run_result = lambda activity: {"activity_id": activity.get("id")}
    coach_agent_module.coaching_reply = fake_coaching_reply
    coach_agent_module.current_garmin_context = lambda: str(
        (case.get("initial_context") or {}).get("garmin_context") or "Garmin context unavailable."
    )
    coach_agent_module.normalize_post_run_feedback = fake_normalize_post_run_feedback
    coach_agent_module.resolve_pending_question = fake_resolve_pending_question
    coach_agent_module.save_synced_run_detail = lambda summary, detail: None
    try:
        agent = coach_agent_module.CoachAgent(
            strava_client=_EvalStrava(case),
            state=state,
            save_state=lambda: None,
        )
        for turn in case.get("turns") or []:
            if turn.get("action") == "check_new_runs":
                replies.extend(agent.check_new_runs(force=bool(turn.get("force", True))))
            elif "user_message" in turn:
                replies.extend(agent.handle_message(str(turn["user_message"]), source="eval"))
            else:
                raise RuntimeError(f"Unsupported coach_agent eval turn: {turn!r}")
    finally:
        coach_agent_module.append_post_run_feedback = original_append_post_run_feedback
        coach_agent_module.append_run_result = original_append_run_result
        coach_agent_module.coaching_reply = original_coaching_reply
        coach_agent_module.current_garmin_context = original_current_garmin_context
        coach_agent_module.normalize_post_run_feedback = original_normalize_post_run_feedback
        coach_agent_module.resolve_pending_question = original_resolve_pending_question
        coach_agent_module.save_synced_run_detail = original_save_synced_run_detail

    reply = "\n\n".join(replies)
    checks = score_coach_agent_case(case, replies, saved_feedback, state)
    return EvalResult(
        name=str(case.get("name") or "unnamed"),
        passed=all(check.passed for check in checks),
        reply=reply,
        saved_plans=[],
        tool_calls=[],
        checks=checks,
        saved_feedback=saved_feedback,
    )


class _EvalStrava:
    def __init__(self, case: dict[str, Any]):
        self.activities = list(case.get("strava_activities") or [])
        self.details = {
            str(key): value for key, value in (case.get("strava_details") or {}).items()
        }

    def recent_activities(self, days: int = 28) -> list[dict[str, Any]]:
        return self.activities

    def detailed_activity(self, activity_id: Any) -> dict[str, Any]:
        return self.details.get(str(activity_id), {"id": activity_id, "type": "Run"})


def _run_case_model_call(
    case: dict[str, Any],
    context: dict[str, Any],
    reply_func: ReplyFunc | None,
) -> str:
    if reply_func:
        return reply_func(
            case["user_message"],
            training_summary=context.get("training_summary", ""),
            recent_runs=context.get("recent_runs", ""),
            weekly_plan=context.get("weekly_plan", ""),
            training_goal=context.get("training_goal", ""),
            coach_log=context.get("coach_log", ""),
            garmin_context=context.get("garmin_context", ""),
            tools_enabled=True,
            temperature=eval_temperature(),
        )
    if case.get("input_kind") == "image":
        image_path = Path(case["image_path"])
        if not image_path.is_absolute():
            image_path = Path.cwd() / image_path
        return openai_client.image_coaching_reply(
            case["user_message"],
            image_bytes=image_path.read_bytes(),
            mime_type=case.get("mime_type", "image/png"),
            training_summary=context.get("training_summary", ""),
            recent_runs=context.get("recent_runs", ""),
            weekly_plan=context.get("weekly_plan", ""),
            training_goal=context.get("training_goal", ""),
            coach_log=context.get("coach_log", ""),
            garmin_context=context.get("garmin_context", ""),
            temperature=eval_temperature(),
        )
    return openai_client.coaching_reply(
        case["user_message"],
        training_summary=context.get("training_summary", ""),
        recent_runs=context.get("recent_runs", ""),
        weekly_plan=context.get("weekly_plan", ""),
        training_goal=context.get("training_goal", ""),
        coach_log=context.get("coach_log", ""),
        garmin_context=context.get("garmin_context", ""),
        tools_enabled=True,
        temperature=eval_temperature(),
    )


def score_plan_adjustment(
    case: dict[str, Any],
    saved_plans: list[str],
) -> list[EvalCheck]:
    expected = (case.get("expected") or {}).get("plan") or {}
    checks = [
        EvalCheck(
            len(saved_plans) == 1,
            f"expected exactly one save_weekly_plan call; got {len(saved_plans)}",
        )
    ]
    if len(saved_plans) != 1:
        return checks

    saved_text = saved_plans[0]
    saved = parse_weekly_plan(saved_text)
    initial = parse_weekly_plan((case.get("initial_context") or {}).get("weekly_plan", ""))

    for day in expected.get("required_days", []):
        checks.append(EvalCheck(day in saved, f"saved plan includes {day}"))

    for day, terms in (expected.get("must_include") or {}).items():
        workout = saved.get(day, "")
        for term in terms:
            checks.append(
                EvalCheck(
                    _contains_loose(workout, str(term)),
                    f"{day} includes {term!r}; got {workout!r}",
                )
            )

    for day, terms in (expected.get("must_not_include") or {}).items():
        workout = saved.get(day, "")
        for term in terms:
            checks.append(
                EvalCheck(
                    not _contains_loose(workout, str(term)),
                    f"{day} does not include {term!r}; got {workout!r}",
                )
            )

    for day in expected.get("must_preserve_days", []):
        checks.append(
            EvalCheck(
                _normalize(saved.get(day, "")) == _normalize(initial.get(day, "")),
                f"{day} preserved; expected {initial.get(day, '')!r}, got {saved.get(day, '')!r}",
            )
        )
    return checks


def score_case(
    case: dict[str, Any],
    saved_plans: list[str],
    saved_goals: list[str],
    tool_calls: list[dict[str, Any]],
    reply: str,
    judge_func: JudgeFunc | None = None,
) -> list[EvalCheck]:
    checks: list[EvalCheck] = []
    if case.get("expected"):
        checks.extend(score_expected(case, saved_plans, saved_goals, tool_calls, reply))
    if case.get("judge"):
        checks.extend(judge_reply(case, reply, judge_func=judge_func))
    checks.append(EvalCheck(bool(reply.strip()), "model returned a non-empty reply"))
    return checks


def score_coach_agent_case(
    case: dict[str, Any],
    replies: list[str],
    saved_feedback: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[EvalCheck]:
    expected = case.get("expected") or {}
    checks: list[EvalCheck] = []

    for index, turn_expected in enumerate(expected.get("turns") or []):
        reply = replies[index] if index < len(replies) else ""
        checks.append(EvalCheck(bool(reply), f"turn {index + 1} returned a reply"))
        checks.extend(
            _prefix_checks(
                score_reply_rules(turn_expected, reply),
                prefix=f"turn {index + 1}: ",
            )
        )

    feedback_expected = expected.get("feedback") or {}
    if feedback_expected:
        expected_count = feedback_expected.get("count")
        if expected_count is not None:
            checks.append(
                EvalCheck(
                    len(saved_feedback) == int(expected_count),
                    f"saved feedback count is {expected_count}; got {len(saved_feedback)}",
                )
            )
        if saved_feedback:
            entry = saved_feedback[-1]
            for key, expected_value in (feedback_expected.get("fields") or {}).items():
                checks.append(
                    EvalCheck(
                        entry.get(key) == expected_value,
                        f"saved feedback {key} is {expected_value!r}; got {entry.get(key)!r}",
                    )
                )

    state_expected = expected.get("state") or {}
    if "pending_post_run_feedback" in state_expected:
        should_have_pending = bool(state_expected["pending_post_run_feedback"])
        checks.append(
            EvalCheck(
                _has_pending_post_run_feedback(state) == should_have_pending,
                f"pending_post_run_feedback present is {should_have_pending}",
            )
        )

    checks.append(EvalCheck(bool(replies), "agent produced at least one reply"))
    return checks


def _has_pending_post_run_feedback(state: dict[str, Any]) -> bool:
    pending = state.get("pending_question")
    if isinstance(pending, dict) and pending.get("kind") == "post_run_feedback":
        return True
    return "pending_post_run_feedback" in state


def _prefix_checks(checks: list[EvalCheck], *, prefix: str) -> list[EvalCheck]:
    return [EvalCheck(check.passed, prefix + check.message) for check in checks]


def score_expected(
    case: dict[str, Any],
    saved_plans: list[str],
    saved_goals: list[str],
    tool_calls: list[dict[str, Any]],
    reply: str,
) -> list[EvalCheck]:
    expected = case.get("expected") or {}
    checks = score_tool_calls(expected, tool_calls)
    if _expects_tool_called(expected, "save_weekly_plan") or _expects_tool_called(
        expected, "update_weekly_plan_days"
    ):
        checks.extend(score_plan_adjustment(case, saved_plans))
    if _expects_tool_called(expected, "update_training_goal"):
        checks.extend(score_goal_update(expected, saved_goals))
    checks.extend(score_reply_rules(expected, reply))
    return checks


def score_goal_update(expected: dict[str, Any], saved_goals: list[str]) -> list[EvalCheck]:
    goal_expected = expected.get("goal") or {}
    checks = [
        EvalCheck(
            len(saved_goals) == 1,
            f"expected exactly one update_training_goal call; got {len(saved_goals)}",
        )
    ]
    if len(saved_goals) != 1:
        return checks
    saved_goal = saved_goals[0]
    for term in goal_expected.get("must_include", []):
        checks.append(
            EvalCheck(
                _contains_loose(saved_goal, str(term)),
                f"saved goal includes {term!r}; got {saved_goal!r}",
            )
        )
    for term in goal_expected.get("must_not_include", []):
        checks.append(
            EvalCheck(
                not _contains_loose(saved_goal, str(term)),
                f"saved goal does not include {term!r}; got {saved_goal!r}",
            )
        )
    for pattern in goal_expected.get("must_not_match", []):
        checks.append(
            EvalCheck(
                re.search(str(pattern), saved_goal, flags=re.MULTILINE) is None,
                f"saved goal does not match /{pattern}/",
            )
        )
    return checks


def score_reply_rules(expected: dict[str, Any], reply: str) -> list[EvalCheck]:
    checks: list[EvalCheck] = []
    if "reply_max_chars" in expected:
        limit = int(expected["reply_max_chars"])
        checks.append(
            EvalCheck(
                len(reply) <= limit,
                f"reply length <= {limit}; got {len(reply)}",
            )
        )
    for term in expected.get("reply_must_include", []):
        checks.append(
            EvalCheck(
                str(term).lower() in reply.lower(),
                f"reply includes {term!r}",
            )
        )
    for pattern in expected.get("reply_must_match", []):
        checks.append(
            EvalCheck(
                re.search(str(pattern), reply, flags=re.MULTILINE | re.IGNORECASE) is not None,
                f"reply matches /{pattern}/",
            )
        )
    for term in expected.get("reply_must_not_include", []):
        checks.append(
            EvalCheck(
                str(term).lower() not in reply.lower(),
                f"reply does not include {term!r}",
            )
        )
    for pattern in expected.get("reply_must_not_match", []):
        checks.append(
            EvalCheck(
                re.search(str(pattern), reply, flags=re.MULTILINE) is None,
                f"reply does not match /{pattern}/",
            )
        )
    return checks


def judge_reply(
    case: dict[str, Any],
    reply: str,
    judge_func: JudgeFunc | None = None,
) -> list[EvalCheck]:
    result = (judge_func or run_judge_model)(case, reply)
    passed = bool(result.get("passed"))
    rationale = str(result.get("rationale") or "").strip()
    failures = result.get("failures") or []
    if isinstance(failures, list):
        failures_text = "; ".join(str(failure) for failure in failures if str(failure).strip())
    else:
        failures_text = str(failures).strip()
    message = "judge passed" if passed else "judge failed"
    if failures_text:
        message += f"; failures: {failures_text}"
    if rationale:
        message += f" ({rationale})"
    return [EvalCheck(passed, message)]


def run_judge_model(case: dict[str, Any], reply: str) -> dict[str, Any]:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for judge-model evals.")

    judge = case.get("judge") or {}
    payload = {
        "model": os.environ.get("OPENAI_EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
        "instructions": (
            "You are grading a running coach bot reply for an evaluation suite. "
            "Return only valid JSON with keys: passed, rationale, failures. "
            "passed must be a boolean. failures must be a list of unmet criteria, empty when passed. "
            "Judge only against the criteria and pass_condition. The rationale must be one short sentence."
        ),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "case_name": case.get("name"),
                                "user_message": case.get("user_message"),
                                "initial_context": case.get("initial_context") or {},
                                "tool_results": case.get("tool_results") or {},
                                "reply": reply,
                                "criteria": judge.get("criteria", []),
                                "pass_condition": judge.get("pass_condition", ""),
                            },
                            indent=2,
                        ),
                    }
                ],
            }
        ],
        "temperature": eval_temperature(),
    }
    response = openai_client._post_json(openai_client.OPENAI_RESPONSES_URL, payload, api_key)
    text = openai_client._extract_output_text(response)
    return _parse_judge_response(text)


def score_tool_calls(
    expected: dict[str, Any],
    tool_calls: list[dict[str, Any]],
) -> list[EvalCheck]:
    checks: list[EvalCheck] = []
    actual_names = [str(call.get("name")) for call in tool_calls]
    tool_expectations = expected.get("tool_calls") or {}

    for spec in _tool_call_specs(tool_expectations.get("called")):
        name = spec["name"]
        matching_calls = [call for call in tool_calls if call.get("name") == name]
        checks.append(
            EvalCheck(
                bool(matching_calls),
                f"expected {name} to be called; got {actual_names}",
            )
        )
        if matching_calls:
            checks.extend(score_tool_arguments(name, matching_calls[0], spec))

    for raw_group in tool_expectations.get("called_any", []):
        group = _tool_call_specs(raw_group)
        names = [spec["name"] for spec in group]
        matching_calls = [call for call in tool_calls if call.get("name") in names]
        checks.append(
            EvalCheck(
                bool(matching_calls),
                f"expected one of {names} to be called; got {actual_names}",
            )
        )

    for spec in _tool_call_specs(tool_expectations.get("not_called")):
        name = spec["name"]
        matching_calls = [call for call in tool_calls if call.get("name") == name]
        checks.append(
            EvalCheck(
                not matching_calls,
                f"expected {name} not to be called; got {actual_names}",
            )
        )
    return checks


def score_tool_arguments(
    name: str,
    call: dict[str, Any],
    spec: dict[str, Any],
) -> list[EvalCheck]:
    expected_args = spec.get("arguments") or {}
    actual_args = call.get("arguments") or {}
    checks: list[EvalCheck] = []
    for key, expected_value in expected_args.items():
        if key == "days_min":
            actual_value = int(actual_args.get("days") or 0)
            checks.append(
                EvalCheck(
                    actual_value >= int(expected_value),
                    f"{name} days >= {expected_value}; got {actual_args.get('days')}",
                )
            )
            continue
        checks.append(
            EvalCheck(
                actual_args.get(key) == expected_value,
                f"{name} {key} is {expected_value!r}; got {actual_args.get(key)!r}",
            )
        )
    return checks


def _expects_tool_called(expected: dict[str, Any], name: str) -> bool:
    tool_expectations = expected.get("tool_calls") or {}
    return any(
        spec["name"] == name for spec in _tool_call_specs(tool_expectations.get("called"))
    ) or any(
        any(spec["name"] == name for spec in _tool_call_specs(group))
        for group in tool_expectations.get("called_any", [])
    )


def _tool_call_specs(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    raw_specs = value if isinstance(value, list) else [value]
    specs: list[dict[str, Any]] = []
    for raw in raw_specs:
        if isinstance(raw, str):
            specs.append({"name": raw})
        elif isinstance(raw, dict) and isinstance(raw.get("name"), str):
            specs.append(dict(raw))
        else:
            raise RuntimeError(f"Tool call expectation must be a tool name or object: {raw!r}")
    return specs


def format_eval_results(results: list[EvalResult], debug: bool = False) -> str:
    lines: list[str] = []
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"{status} {result.name}")
        for check in result.checks:
            check_status = "PASS" if check.passed else "FAIL"
            lines.append(f"  {check_status} {check.message}")
        if not debug:
            continue
        if result.saved_plans:
            lines.extend(["", "Saved plan:", result.saved_plans[-1]])
        if result.tool_calls:
            lines.extend(["", "Tool calls:", json.dumps(result.tool_calls, indent=2)])
        if result.saved_feedback:
            lines.extend(["", "Saved feedback:", json.dumps(result.saved_feedback, indent=2)])
        if result.reply:
            lines.extend(["", "Reply:", result.reply])
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    lines.extend(["", f"Summary: {passed} passed, {failed} failed"])
    return "\n".join(lines)


def _tool_result(case: dict[str, Any], name: str) -> str:
    results = case.get("tool_results") or {}
    value = results.get(name)
    if isinstance(value, str):
        return value
    return f"No fixture result configured for {name}."


def _parse_judge_response(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Judge response was not valid JSON: {text!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Judge response must be a JSON object: {text!r}")
    return parsed


def eval_temperature() -> float:
    raw = os.environ.get("OPENAI_EVAL_TEMPERATURE")
    if raw is None:
        return DEFAULT_EVAL_TEMPERATURE
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"OPENAI_EVAL_TEMPERATURE must be a number, got {raw!r}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="running-agent evals")
    parser.add_argument(
        "--case",
        default=None,
        help="Eval case name or JSON path. Defaults to all cases.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include saved plans, tool calls, and model replies in eval output.",
    )
    args = parser.parse_args(argv)
    results = run_evals(args.case)
    print(format_eval_results(results, debug=args.debug))
    return 0 if all(result.passed for result in results) else 1


def _all_case_paths() -> list[Path]:
    return sorted(CASE_DIR.glob("*.json"))


def _case_path(case_name: str | None) -> Path:
    if not case_name:
        raise RuntimeError("case_name is required")
    path = Path(case_name)
    if path.suffix == ".json":
        return path
    matches = sorted(CASE_DIR.glob(f"{case_name}*.json"))
    if not matches:
        raise RuntimeError(f"No eval case found for {case_name!r} in {CASE_DIR}")
    if len(matches) > 1:
        raise RuntimeError(f"Eval case name {case_name!r} is ambiguous: {matches}")
    return matches[0]


def _contains_loose(value: str, term: str) -> bool:
    return _normalize(term) in _normalize(value)


def _normalize(value: str) -> str:
    return "".join(value.lower().split())


if __name__ == "__main__":
    raise SystemExit(main())
