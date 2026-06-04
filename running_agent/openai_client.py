from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .athlete_profile import append_coaching_preference, athlete_profile_context
from .auth import load_env_file
from .coach_reflection import coach_reflection_context
from .coach_time import coach_now
from .coaching_guidance import (
    COACHING_STANCE_RUBRIC,
    GARMIN_COACHING_RUBRIC,
    TRAINING_PROGRESSION_RUBRIC,
)
from .garmin_context import safe_garmin_weekly_context
from .goal_store import save_training_goal
from .plan_store import save_weekly_plan
from .strava_tools import get_local_run_details, query_local_runs

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.4-mini"
REMEMBER_NOTE_TOOL = {
    "type": "function",
    "name": "remember_coaching_note",
    "description": (
        "Store a durable coaching note about the athlete for future coaching. Use this when "
        "the athlete explicitly states a preference, constraint, recurring issue, important "
        "context, or something they ask you to remember. Do not store ordinary one-off questions "
        "or sensitive medical details. For example, if the athlete says they prefer quality "
        "sessions on Wednesdays or long runs on Saturdays, store that preference."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "note": {
                "type": "string",
                "description": "A concise note to remember for future coaching.",
            }
        },
        "required": ["note"],
        "additionalProperties": False,
    },
    "strict": True,
}
UPDATE_GOAL_TOOL = {
    "type": "function",
    "name": "update_training_goal",
    "description": (
        "Save a revised overall training goal for future coaching. Use this when the athlete "
        "states a durable goal, race target, target time, goal race date, priority, or a change "
        "to an existing goal. Write a complete updated goal statement that preserves still-relevant "
        "existing goal details and incorporates the new information. Do not use this for ordinary "
        "workout preferences; use remember_coaching_note for those."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "The complete revised overall training goal to save for future coaching."
                ),
            }
        },
        "required": ["goal"],
        "additionalProperties": False,
    },
    "strict": True,
}
SAVE_WEEKLY_PLAN_TOOL = {
    "type": "function",
    "name": "save_weekly_plan",
    "description": (
        "Save a complete weekly training plan for future coaching. Use this when the athlete "
        "provides, revises, or approves a weekly plan, including natural messages like 'here is "
        "my plan for next week'. Convert the plan into clear plain text with one line for each "
        "planned day. Preserve runner shorthand such as '2mi WU, 6x400m, CD'. Do not use this "
        "for casual workout ideas unless the athlete indicates the plan should be saved."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": (
                    "The complete weekly plan text to save, ideally with one line per planned day."
                ),
            }
        },
        "required": ["plan"],
        "additionalProperties": False,
    },
    "strict": True,
}
QUERY_LOCAL_RUNS_TOOL = {
    "type": "function",
    "name": "query_local_runs",
    "description": (
        "Search synced local Strava runs when the athlete asks for activity facts that are not "
        "available in the provided recent context, such as their last race, race distances, "
        "older runs, or runs matching a name/date. Returns compact facts and activity IDs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Optional search terms to match against activity name or date. Leave empty "
                    "for broad queries like latest race."
                ),
            },
            "days": {
                "type": "integer",
                "description": "How many days back to search. Use 365 unless the athlete asks otherwise.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of matching runs to return, usually 3 to 8.",
            },
            "races_only": {
                "type": "boolean",
                "description": "Whether to return only race-like runs.",
            },
        },
        "required": ["query", "days", "limit", "races_only"],
        "additionalProperties": False,
    },
    "strict": True,
}
GET_LOCAL_RUN_DETAILS_TOOL = {
    "type": "function",
    "name": "get_local_run_details",
    "description": (
        "Return detailed synced Strava run context, including lap/split data when available. "
        "Use this when the athlete asks about splits, reps, laps, workout segments, or details "
        "of a specific run such as the latest run, latest race, a date, query, or activity ID."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "One of latest_run, latest_race, activity_id, date, or query.",
            },
            "activity_id": {
                "type": "string",
                "description": "Activity ID when selector is activity_id; otherwise empty.",
            },
            "query": {
                "type": "string",
                "description": "Search terms when selector is query; otherwise optional.",
            },
            "date": {
                "type": "string",
                "description": "YYYY-MM-DD date when selector is date; otherwise empty.",
            },
            "days": {
                "type": "integer",
                "description": "How many days back to search. Use 365 unless the athlete asks otherwise.",
            },
        },
        "required": ["selector", "activity_id", "query", "date", "days"],
        "additionalProperties": False,
    },
    "strict": True,
}
GET_GARMIN_READINESS_TOOL = {
    "type": "function",
    "name": "get_garmin_readiness",
    "description": (
        "Return today's live Garmin readiness context, including readiness, sleep, HRV, stress, "
        "resting HR, Body Battery, and athlete baseline ranges from cached completed days when "
        "available. Use this when the athlete asks about recovery, readiness, sleep, HRV, body "
        "battery, stress, or whether today's training should be adjusted."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    "strict": True,
}
GET_GARMIN_TREND_TOOL = {
    "type": "function",
    "name": "get_garmin_recovery_trend",
    "description": (
        "Return recent Garmin recovery trend context from cached completed days. Use this when "
        "the athlete asks about recent recovery trends, the last week of Garmin data, HRV trends, "
        "sleep trends, stress trends, resting HR trends, or whether fatigue is accumulating over "
        "several days."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "How many recent days to summarize. Use 7 unless the athlete asks otherwise.",
            }
        },
        "required": ["days"],
        "additionalProperties": False,
    },
    "strict": True,
}


def coaching_reply(
    message: str,
    training_summary: str,
    recent_runs: str,
    weekly_plan: str | None = None,
    training_goal: str | None = None,
    coach_log: str | None = None,
    garmin_context: str | None = None,
    conversation: list[dict[str, str]] | None = None,
    tools_enabled: bool = True,
    max_output_tokens: int = 650,
    include_coach_reflection: bool = True,
) -> str:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_reply(message, training_summary)

    prompt_parts = [
        "Current local date:",
        coach_now().strftime("%A, %B %-d, %Y"),
        "",
        "The athlete asked:",
        message,
        "",
        "Current training summary:",
        training_summary,
        "",
        "Recent runs:",
        recent_runs,
        "",
        "Athlete-specific profile:",
        athlete_profile_context(),
        "",
        COACHING_STANCE_RUBRIC,
        "",
        GARMIN_COACHING_RUBRIC,
        "",
        TRAINING_PROGRESSION_RUBRIC,
    ]
    if include_coach_reflection:
        prompt_parts.extend(
            [
                "",
                "Coach's private current training thesis:",
                coach_reflection_context(),
            ]
        )
    if weekly_plan:
        prompt_parts.extend(["", "Athlete-provided weekly plan:", weekly_plan])
    if training_goal:
        prompt_parts.extend(["", "Athlete-provided overall training goal:", training_goal])
    if coach_log:
        prompt_parts.extend(["", "Recent coach log:", coach_log])
    if garmin_context:
        prompt_parts.extend(["", "Garmin readiness context:", garmin_context])
    if conversation:
        prior = "\n".join(f"{item['role']}: {item['content']}" for item in conversation[-8:])
        prompt_parts.extend(["", "Recent Telegram conversation:", prior])

    payload = {
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "instructions": (
            "You are a practical running coach chatting over Telegram. Use the provided Strava "
            "context and weekly plan, be specific, concise, and direct. Your job is to coach the "
            "athlete toward their stated goal, not merely summarize training or sound encouraging. "
            "Praise clearly when execution earns it, but challenge choices and patterns that do "
            "not serve the goal. Do not manufacture criticism. When enough context is available, "
            "think critically about whether the stated goal looks realistic from the athlete's "
            "recent training, recovery, timeline, and workout execution. If the goal looks "
            "realistic, explain the evidence and push the next appropriate progression. If it "
            "looks uncertain or unlikely, say that plainly and identify what has to change. "
            "When a weekly plan "
            "is provided, first align completed runs to the plan by the run's local date and "
            "weekday. If the run happened on Friday, compare it to Friday's planned workout, "
            "not Monday's. If the matching plan day is missing or ambiguous, say that instead "
            "of guessing. Compare completed runs against the intended workout without being rigid. "
            "Lap-by-lap data is most important for structured workouts, interval sessions, tempo "
            "runs, races, and other quality days. For easy runs or steady aerobic runs, do not "
            "over-analyze individual laps; use laps only as secondary context for pacing, drift, "
            "or obvious anomalies. "
            "Use the overall training goal to frame tradeoffs, priorities, and how aggressive "
            "the athlete should be. Aim for appropriately challenging training within sound "
            "progression guardrails, and distinguish normal training fatigue from recovery debt. "
            "Respect the scope and timing of the athlete's question. If they ask for a Garmin "
            "readout or trend, answer that readout first and do not pivot into workout execution "
            "instructions unless they ask what to do, ask whether to adjust training, or the "
            "recovery data clearly warrants a training change. If recent Strava context shows "
            "today's planned workout has already been completed, discuss it in the past tense "
            "rather than telling the athlete to do it. Avoid vague status labels like 'usable'; "
            "say concretely whether the metrics look steady, better than baseline, worse than "
            "baseline, mixed, or concerning. "
            "Garmin readiness, Body Battery, HRV, stress, sleep, resting HR, and VO2 max are "
            "context to interpret alongside the plan, recent workload, and athlete-specific "
            "profile; do not let one generic Garmin label override the training plan by itself. "
            "When the athlete asks about Garmin readiness, recovery, sleep, HRV, stress, resting "
            "HR, Body Battery, or whether recovery metrics should change today's training, call "
            "get_garmin_readiness or get_garmin_recovery_trend before answering unless the needed "
            "Garmin context is already present in the prompt. "
            "When the athlete states a durable coaching preference, constraint, recurring "
            "pattern, or asks you to remember something, call remember_coaching_note before "
            "answering. Examples include preferred workout days, long-run days, scheduling "
            "constraints, recurring recovery issues, and coaching style preferences. Treat "
            "general statements like 'I prefer...', 'I usually...', 'I generally...', and "
            "'keep in mind...' as likely memory candidates when they will help future coaching. "
            "After storing a note, briefly acknowledge it in the normal coaching reply. "
            "When the athlete states or changes a durable training goal, race target, target "
            "time, goal race date, or major priority, call update_training_goal before answering. "
            "Use the current overall training goal context to rewrite a complete updated goal "
            "statement rather than saving only a fragment. After updating the goal, briefly "
            "acknowledge the change in the normal coaching reply. "
            "When the athlete provides, revises, or approves a weekly training plan to use for "
            "future coaching, call save_weekly_plan before answering. Rewrite natural plan text "
            "into a complete plain-text weekly plan with one line per planned day, preserving "
            "runner shorthand. After saving the plan, briefly acknowledge it in the normal "
            "coaching reply. "
            "When the athlete asks for Strava activity facts that are not already present in "
            "the provided recent context, call query_local_runs or get_local_run_details before "
            "answering. Use query_local_runs for broad searches like last race distance or older "
            "runs matching a date/name. Use get_local_run_details for splits, laps, reps, workout "
            "segments, or detailed questions about a specific run such as the latest run. Do not "
            "guess from memory when local synced Strava data can answer the question. "
            "Write in plain text for Telegram. Do not use Markdown formatting, including "
            "asterisk bold, headings, tables, or bullet symbols that require Markdown rendering. "
            "Write like a coach texting the athlete, not like a report. Do not use section "
            "headers or label-style phrases such as 'Coach take:', 'What stands out:', "
            "'Bottom line:', 'Bigger picture:', 'Takeaway:', or 'Next step:'. Work those ideas "
            "into natural sentences instead. "
            "Do not diagnose injuries or give medical certainty; recommend rest or a clinician "
            "when pain, illness, or injury risk comes up."
        ),
        "input": "\n".join(prompt_parts),
        "max_output_tokens": max_output_tokens,
    }
    if tools_enabled:
        payload["tools"] = [
            REMEMBER_NOTE_TOOL,
            UPDATE_GOAL_TOOL,
            SAVE_WEEKLY_PLAN_TOOL,
            QUERY_LOCAL_RUNS_TOOL,
            GET_LOCAL_RUN_DETAILS_TOOL,
            GET_GARMIN_READINESS_TOOL,
            GET_GARMIN_TREND_TOOL,
        ]
        payload["tool_choice"] = "auto"
    response = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
    if tools_enabled:
        response = _handle_tool_calls(response, payload, api_key)
    text = _extract_output_text(response)
    if not text:
        raise RuntimeError("OpenAI response did not include text output.")
    return text.strip()


def _handle_tool_calls(
    response: dict[str, Any],
    original_payload: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    tool_outputs = []
    for call in _function_calls(response):
        if call.get("name") == "remember_coaching_note":
            output = _execute_remember_note_tool(call)
        elif call.get("name") == "update_training_goal":
            output = _execute_update_goal_tool(call)
        elif call.get("name") == "save_weekly_plan":
            output = _execute_save_weekly_plan_tool(call)
        elif call.get("name") == "query_local_runs":
            output = _execute_query_local_runs_tool(call)
        elif call.get("name") == "get_local_run_details":
            output = _execute_get_local_run_details_tool(call)
        elif call.get("name") == "get_garmin_readiness":
            output = _execute_get_garmin_readiness_tool(call)
        elif call.get("name") == "get_garmin_recovery_trend":
            output = _execute_get_garmin_trend_tool(call)
        else:
            continue
        if output:
            tool_outputs.append(output)

    if not tool_outputs:
        return response

    followup_payload = {
        "model": original_payload["model"],
        "instructions": original_payload["instructions"],
        "input": tool_outputs,
        "max_output_tokens": original_payload.get("max_output_tokens", 650),
    }
    if response.get("id"):
        followup_payload["previous_response_id"] = response["id"]
    return _post_json(OPENAI_RESPONSES_URL, followup_payload, api_key)


def _execute_remember_note_tool(call: dict[str, Any]) -> dict[str, str] | None:
    note = _tool_argument(call, "note")
    if not note:
        return None
    append_coaching_preference(note)
    return _tool_output(call["call_id"], {"saved": True})


def _execute_update_goal_tool(call: dict[str, Any]) -> dict[str, str] | None:
    goal = _tool_argument(call, "goal")
    if not goal:
        return None
    save_training_goal(goal)
    return _tool_output(call["call_id"], {"saved": True})


def _execute_save_weekly_plan_tool(call: dict[str, Any]) -> dict[str, str] | None:
    plan = _tool_argument(call, "plan")
    if not plan:
        return None
    save_weekly_plan(plan)
    return _tool_output(call["call_id"], {"saved": True})


def _execute_query_local_runs_tool(call: dict[str, Any]) -> dict[str, str] | None:
    arguments = _tool_arguments(call)
    if arguments is None:
        return None
    result = query_local_runs(
        query=str(arguments.get("query") or ""),
        days=_int_argument(arguments.get("days"), default=365),
        limit=_int_argument(arguments.get("limit"), default=8),
        races_only=_bool_argument(arguments.get("races_only")),
    )
    return _tool_output(call["call_id"], {"result": result})


def _execute_get_local_run_details_tool(call: dict[str, Any]) -> dict[str, str] | None:
    arguments = _tool_arguments(call)
    if arguments is None:
        return None
    result = get_local_run_details(
        selector=str(arguments.get("selector") or "latest_run"),
        activity_id=str(arguments.get("activity_id") or ""),
        query=str(arguments.get("query") or ""),
        date=str(arguments.get("date") or ""),
        days=_int_argument(arguments.get("days"), default=365),
    )
    return _tool_output(call["call_id"], {"result": result})


def _execute_get_garmin_readiness_tool(call: dict[str, Any]) -> dict[str, str]:
    from .daily_checkin import current_garmin_context

    return _tool_output(call["call_id"], {"result": current_garmin_context()})


def _execute_get_garmin_trend_tool(call: dict[str, Any]) -> dict[str, str] | None:
    arguments = _tool_arguments(call)
    if arguments is None:
        return None
    days = max(1, min(_int_argument(arguments.get("days"), default=7), 45))
    return _tool_output(call["call_id"], {"result": safe_garmin_weekly_context(days=days)})


def _tool_output(call_id: str, output: dict[str, Any]) -> dict[str, str]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(output),
    }


def _function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in response.get("output", [])
        if item.get("type") == "function_call" and isinstance(item.get("call_id"), str)
    ]


def _tool_argument(call: dict[str, Any], name: str) -> str | None:
    parsed = _tool_arguments(call)
    if parsed is None:
        return None
    value = parsed.get(name)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _tool_arguments(call: dict[str, Any]) -> dict[str, Any] | None:
    arguments = call.get("arguments")
    if not isinstance(arguments, str):
        return None
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _int_argument(value: Any, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _bool_argument(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _post_json(url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8")
        raise RuntimeError(f"OpenAI request failed with HTTP {error.code}: {body}") from error


def _extract_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _fallback_reply(message: str, training_summary: str) -> str:
    return (
        "I can chat as your coach once OPENAI_API_KEY is set. For now, here is the current "
        "training readout I can see from Strava:\n\n"
        f"{training_summary}\n\n"
        "Rule of thumb for this question: keep the next run easy unless the last few days have "
        "felt fresh, and add volume gradually before adding intensity."
    )
