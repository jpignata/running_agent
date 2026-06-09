from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import openai_client
from .plan_store import parse_weekly_plan

CASE_DIR = Path(__file__).resolve().parent.parent / "evals" / "cases"
DEFAULT_CASE = "adjust_existing_weekly_plan"


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
    checks: list[EvalCheck]


ReplyFunc = Callable[..., str]


def run_evals(case_name: str | None = None) -> list[EvalResult]:
    case_paths = [_case_path(case_name or DEFAULT_CASE)]
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
    original_save_weekly_plan = openai_client.save_weekly_plan

    def capture_save_weekly_plan(plan_text: str):
        saved_plans.append(plan_text)
        return {"text": plan_text}

    openai_client.save_weekly_plan = capture_save_weekly_plan
    try:
        context = case.get("initial_context") or {}
        reply = _run_case_model_call(case, context, reply_func)
    finally:
        openai_client.save_weekly_plan = original_save_weekly_plan

    checks = score_plan_adjustment(case, saved_plans, reply)
    return EvalResult(
        name=str(case.get("name") or "unnamed"),
        passed=all(check.passed for check in checks),
        reply=reply,
        saved_plans=saved_plans,
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
        if result.reply:
            lines.extend(["", "Reply:", result.reply])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="running-agent evals")
    parser.add_argument(
        "--case",
        default=DEFAULT_CASE,
        help="Eval case name or JSON path. Defaults to adjust_existing_weekly_plan.",
    )
    args = parser.parse_args(argv)
    results = run_evals(args.case)
    print(format_eval_results(results))
    return 0 if all(result.passed for result in results) else 1


def _case_path(case_name: str) -> Path:
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
