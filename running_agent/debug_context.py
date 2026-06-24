from __future__ import annotations

import os
from dataclasses import dataclass

from .activity_format import recent_runs_context
from .athlete_profile import athlete_profile_context
from .coach_prompt import COACHING_TOOLS, build_coaching_input
from .coach_reflection import coach_reflection_context
from .coach_time import coach_now, coach_today
from .feedback import summarize_training
from .goal_readiness import goal_readiness_context
from .goal_store import training_goal_context
from .openai_client import DEFAULT_MODEL
from .plan_store import weekly_plan_context_for_date
from .strava_client import StravaClient

DEFAULT_DEBUG_LOOKBACK_DAYS = 28


@dataclass(frozen=True)
class CoachDebugContext:
    message: str
    model: str
    tools_enabled: bool
    tool_names: list[str]
    training_summary: str
    recent_runs: str
    weekly_plan: str
    training_goal: str
    goal_readiness: str
    athlete_profile: str
    coach_reflection: str
    conversation: list[dict[str, str]]
    assembled_input: str
    prompt_diagnostics: dict[str, int]


def build_chat_debug_context(
    *,
    message: str,
    client: StravaClient,
    lookback_days: int = DEFAULT_DEBUG_LOOKBACK_DAYS,
    conversation: list[dict[str, str]] | None = None,
    tools_enabled: bool = True,
) -> CoachDebugContext:
    conversation = conversation or []
    activities = client.recent_activities(days=lookback_days)
    training_summary = summarize_training(activities, days=lookback_days)
    recent_runs = recent_runs_context(activities)
    weekly_plan = weekly_plan_context_for_date(coach_today())
    training_goal = training_goal_context()
    readiness = goal_readiness_context(activities=activities, days=lookback_days)
    profile = athlete_profile_context()
    reflection = coach_reflection_context()
    assembled_input = build_coaching_input(
        message=message,
        training_summary=training_summary,
        recent_runs=recent_runs,
        weekly_plan=weekly_plan,
        training_goal=training_goal,
        goal_readiness=readiness,
        conversation=conversation,
        athlete_profile_text=profile,
        coach_reflection_text=reflection,
    )
    diagnostics = prompt_diagnostics(
        assembled_input=assembled_input,
        training_summary=training_summary,
        recent_runs=recent_runs,
        weekly_plan=weekly_plan,
        training_goal=training_goal,
        goal_readiness=readiness,
        athlete_profile=profile,
        coach_reflection=reflection,
        conversation=conversation,
        tools_enabled=tools_enabled,
    )
    return CoachDebugContext(
        message=message,
        model=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        tools_enabled=tools_enabled,
        tool_names=[tool["name"] for tool in COACHING_TOOLS] if tools_enabled else [],
        training_summary=training_summary,
        recent_runs=recent_runs,
        weekly_plan=weekly_plan,
        training_goal=training_goal,
        goal_readiness=readiness,
        athlete_profile=profile,
        coach_reflection=reflection,
        conversation=conversation[-8:],
        assembled_input=assembled_input,
        prompt_diagnostics=diagnostics,
    )


def prompt_diagnostics(
    *,
    assembled_input: str,
    training_summary: str,
    recent_runs: str,
    weekly_plan: str,
    training_goal: str,
    goal_readiness: str,
    athlete_profile: str,
    coach_reflection: str,
    conversation: list[dict[str, str]],
    tools_enabled: bool,
) -> dict[str, int]:
    conversation_text = _format_conversation(conversation[-8:])
    return {
        "input_chars": len(assembled_input),
        "estimated_input_tokens": _estimated_tokens(assembled_input),
        "training_summary_chars": len(training_summary),
        "recent_runs_chars": len(recent_runs),
        "weekly_plan_chars": len(weekly_plan),
        "training_goal_chars": len(training_goal),
        "goal_readiness_chars": len(goal_readiness),
        "athlete_profile_chars": len(athlete_profile),
        "coach_reflection_chars": len(coach_reflection),
        "conversation_chars": len(conversation_text),
        "tool_count": len(COACHING_TOOLS) if tools_enabled else 0,
    }


def format_chat_debug_context(context: CoachDebugContext) -> str:
    sections = [
        _section(
            "Debug Metadata",
            "\n".join(
                [
                    f"Current local date: {coach_now().strftime('%A, %B %-d, %Y')}",
                    f"Model: {context.model}",
                    f"Tools enabled: {_yes_no(context.tools_enabled)}",
                    "Tools: " + (", ".join(context.tool_names) if context.tool_names else "none"),
                    _format_prompt_diagnostics(context.prompt_diagnostics),
                    (
                        "Garmin: not included in the initial prompt unless supplied by a caller; "
                        "available through Garmin tools when tools are enabled."
                    ),
                ]
            ),
        ),
        _section("User Message", context.message),
        _section("Training Summary", context.training_summary),
        _section("Recent Runs", context.recent_runs),
        _section("Matched Weekly Plan", context.weekly_plan),
        _section("Training Goal", context.training_goal),
        _section("Goal Readiness", context.goal_readiness),
        _section("Coaching Notes", context.athlete_profile),
        _section("Coach Reflection", context.coach_reflection),
        _section("Recent Conversation", _format_conversation(context.conversation)),
        _section("Assembled Model Input", context.assembled_input),
    ]
    return "\n\n".join(sections)


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip() if body.strip() else '(empty)'}"


def _format_conversation(conversation: list[dict[str, str]]) -> str:
    if not conversation:
        return "(none)"
    return "\n".join(f"{item['role']}: {item['content']}" for item in conversation)


def _format_prompt_diagnostics(diagnostics: dict[str, int]) -> str:
    return (
        "Prompt size: "
        f"{diagnostics.get('input_chars', 0)} chars, "
        f"~{diagnostics.get('estimated_input_tokens', 0)} tokens, "
        f"{diagnostics.get('tool_count', 0)} tools. "
        "Section chars: "
        f"training {diagnostics.get('training_summary_chars', 0)}, "
        f"runs {diagnostics.get('recent_runs_chars', 0)}, "
        f"plan {diagnostics.get('weekly_plan_chars', 0)}, "
        f"goal {diagnostics.get('training_goal_chars', 0)}, "
        f"readiness {diagnostics.get('goal_readiness_chars', 0)}, "
        f"profile {diagnostics.get('athlete_profile_chars', 0)}, "
        f"reflection {diagnostics.get('coach_reflection_chars', 0)}, "
        f"conversation {diagnostics.get('conversation_chars', 0)}."
    )


def _estimated_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
