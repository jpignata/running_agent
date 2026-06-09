from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import openai_client
from .plan_store import parse_weekly_plan

CASE_DIR = Path(__file__).resolve().parent.parent / "evals" / "cases"


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


ReplyFunc = Callable[..., str]


def run_evals(case_name: str | None = None) -> list[EvalResult]:
    case_paths = [_case_path(case_name)] if case_name else _all_case_paths()
    return [run_behavioral_case(load_case(path)) for path in case_paths]


def load_case(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Eval case must be a JSON object: {path}")
    return data


def run_behavioral_case(
    case: dict[str, Any],
    reply_func: ReplyFunc | None = None,
) -> EvalResult:
    if case.get("type") != "behavioral":
        raise RuntimeError(f"Unsupported eval type: {case.get('type')}")

    saved_plans: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    original_save_weekly_plan = openai_client.save_weekly_plan
    original_query_local_runs = openai_client.query_local_runs
    original_get_local_run_details = openai_client.get_local_run_details

    def capture_save_weekly_plan(plan_text: str):
        saved_plans.append(plan_text)
        return {"text": plan_text}

    def capture_query_local_runs(**kwargs):
        tool_calls.append({"name": "query_local_runs", "arguments": dict(kwargs)})
        return _tool_result(case, "query_local_runs")

    def capture_get_local_run_details(**kwargs):
        tool_calls.append({"name": "get_local_run_details", "arguments": dict(kwargs)})
        return _tool_result(case, "get_local_run_details")

    openai_client.save_weekly_plan = capture_save_weekly_plan
    openai_client.query_local_runs = capture_query_local_runs
    openai_client.get_local_run_details = capture_get_local_run_details
    try:
        context = case.get("initial_context") or {}
        reply = _run_case_model_call(case, context, reply_func)
    finally:
        openai_client.save_weekly_plan = original_save_weekly_plan
        openai_client.query_local_runs = original_query_local_runs
        openai_client.get_local_run_details = original_get_local_run_details

    checks = score_behavioral_case(case, saved_plans, tool_calls, reply)
    return EvalResult(
        name=str(case.get("name") or "unnamed"),
        passed=all(check.passed for check in checks),
        reply=reply,
        saved_plans=saved_plans,
        tool_calls=tool_calls,
        checks=checks,
    )


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
    )


def score_plan_adjustment(
    case: dict[str, Any],
    saved_plans: list[str],
    reply: str,
) -> list[EvalCheck]:
    expected = case.get("expected") or {}
    checks = [
        EvalCheck(
            len(saved_plans) == 1,
            f"expected exactly one {expected.get('tool_call', 'tool')} call; got {len(saved_plans)}",
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

    checks.append(EvalCheck(bool(reply.strip()), "model returned a non-empty reply"))
    return checks


def score_behavioral_case(
    case: dict[str, Any],
    saved_plans: list[str],
    tool_calls: list[dict[str, Any]],
    reply: str,
) -> list[EvalCheck]:
    if case.get("behavior") == "retrieval":
        return score_retrieval_case(case, tool_calls, reply)
    return score_plan_adjustment(case, saved_plans, reply)


def score_retrieval_case(
    case: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    reply: str,
) -> list[EvalCheck]:
    expected = case.get("expected") or {}
    expected_tool = expected.get("tool_call")
    matching_calls = [call for call in tool_calls if call.get("name") == expected_tool]
    checks = [
        EvalCheck(
            bool(matching_calls),
            f"expected {expected_tool} call; got {[call.get('name') for call in tool_calls]}",
        )
    ]
    if matching_calls and expected_tool == "query_local_runs":
        args = matching_calls[0].get("arguments") or {}
        query_expected = expected.get("query_local_runs") or {}
        if "races_only" in query_expected:
            checks.append(
                EvalCheck(
                    args.get("races_only") is query_expected["races_only"],
                    f"query_local_runs races_only is {query_expected['races_only']}; got {args.get('races_only')}",
                )
            )
        if "days_min" in query_expected:
            checks.append(
                EvalCheck(
                    int(args.get("days") or 0) >= int(query_expected["days_min"]),
                    f"query_local_runs days >= {query_expected['days_min']}; got {args.get('days')}",
                )
            )
    for term in expected.get("reply_must_include", []):
        checks.append(
            EvalCheck(
                str(term).lower() in reply.lower(),
                f"reply includes {term!r}",
            )
        )
    checks.append(EvalCheck(bool(reply.strip()), "model returned a non-empty reply"))
    return checks


def format_eval_results(results: list[EvalResult]) -> str:
    lines: list[str] = []
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"{status} {result.name}")
        for check in result.checks:
            check_status = "PASS" if check.passed else "FAIL"
            lines.append(f"  {check_status} {check.message}")
        if result.saved_plans:
            lines.extend(["", "Saved plan:", result.saved_plans[-1]])
        if result.tool_calls:
            lines.extend(["", "Tool calls:", json.dumps(result.tool_calls, indent=2)])
        if result.reply:
            lines.extend(["", "Reply:", result.reply])
    return "\n".join(lines)


def _tool_result(case: dict[str, Any], name: str) -> str:
    results = case.get("tool_results") or {}
    value = results.get(name)
    if isinstance(value, str):
        return value
    return f"No fixture result configured for {name}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="running-agent evals")
    parser.add_argument(
        "--case",
        default=None,
        help="Eval case name or JSON path. Defaults to all cases.",
    )
    args = parser.parse_args(argv)
    results = run_evals(args.case)
    print(format_eval_results(results))
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
