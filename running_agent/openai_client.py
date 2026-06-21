from __future__ import annotations

import base64
import json
import os
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .athlete_profile import append_coaching_preference
from .auth import load_env_file
from .coach_prompt import (
    COACHING_INSTRUCTIONS,
    COACHING_TOOLS,
    build_coaching_input,
    build_coaching_payload,
)
from .garmin_context import safe_garmin_weekly_context
from .goal_store import save_training_goal
from .plan_store import save_weekly_plan, update_weekly_plan_days
from .race_results import save_race_result
from .strava_tools import get_local_run_details, query_local_runs

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"


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
    max_output_tokens: int | None = None,
    include_coach_reflection: bool = True,
    pace_calibration_text: str | None = None,
    temperature: float | None = None,
) -> str:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_reply(message, training_summary)

    payload = build_coaching_payload(
        model=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        message=message,
        training_summary=training_summary,
        recent_runs=recent_runs,
        weekly_plan=weekly_plan,
        training_goal=training_goal,
        coach_log=coach_log,
        garmin_context=garmin_context,
        conversation=conversation,
        tools_enabled=tools_enabled,
        max_output_tokens=max_output_tokens,
        include_coach_reflection=include_coach_reflection,
        pace_calibration_text=pace_calibration_text,
        temperature=temperature,
    )
    response = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
    if tools_enabled:
        response = _handle_tool_calls(response, payload, api_key)
    text = _extract_output_text(response)
    if not text:
        raise RuntimeError("OpenAI response did not include text output.")
    return text.strip()


def image_coaching_reply(
    message: str,
    image_bytes: bytes,
    mime_type: str,
    training_summary: str,
    recent_runs: str,
    weekly_plan: str | None = None,
    training_goal: str | None = None,
    coach_log: str | None = None,
    garmin_context: str | None = None,
    conversation: list[dict[str, str]] | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return (
            "I received the image, but image understanding needs OPENAI_API_KEY to be set. "
            "Add a caption with the key details and I can still coach from text."
        )

    context = build_coaching_input(
        message=message,
        training_summary=training_summary,
        recent_runs=recent_runs,
        weekly_plan=weekly_plan,
        training_goal=training_goal,
        coach_log=coach_log,
        garmin_context=garmin_context,
        conversation=conversation,
    )
    payload = {
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "instructions": (
            COACHING_INSTRUCTIONS
            + " The athlete sent an image. Inspect the image directly and use it as coaching "
            "context. For course screenshots, focus on concrete running implications such as "
            "elevation, turns, terrain, pacing, effort distribution, risk spots, and how it "
            "fits the athlete's current plan and goal. If the image text is unreadable or the "
            "important details are not visible, say what you cannot see and ask for the missing "
            "detail. Do not claim certainty about details that are not visible. If the athlete "
            "asks you to save or update a weekly plan from an image, call save_weekly_plan with "
            "a complete weekly plan. Normalize screenshot or announcement text into concise "
            "workout lines before saving: keep workout substance such as reps, effort, recovery, "
            "warmup, and important timing, but omit UI text, announcement titles, dates already "
            "implied by the target weekday, author names, locations, reactions, club names, and "
            "other source metadata unless the athlete explicitly asks to preserve them. For "
            "example, save 'Wednesday: 5 x 5 min @ threshold or a tiny bit faster, 2 min "
            "recovery; warmup with strides' rather than 'Wednesday: Track workout at Underhill "
            "Sports Complex...'."
        ),
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": context},
                    {
                        "type": "input_image",
                        "image_url": _image_data_url(image_bytes, mime_type),
                    },
                ],
            }
        ],
        "tools": COACHING_TOOLS,
        "tool_choice": "auto",
    }
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    response = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
    response = _handle_tool_calls(response, payload, api_key)
    text = _extract_output_text(response)
    if not text:
        raise RuntimeError("OpenAI response did not include text output.")
    return text.strip()


def normalize_post_run_feedback(message: str) -> dict[str, Any]:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to normalize post-run feedback.")

    payload = {
        "model": os.environ.get("OPENAI_FEEDBACK_MODEL")
        or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "instructions": (
            "Normalize a runner's reply to a post-run feel check. Return only JSON with "
            "keys is_feedback, rpe, legs, pain, notes. is_feedback is true only when the "
            "message is answering how the run felt, including RPE, effort, legs, pain, "
            "soreness, fatigue, breathing, or execution. Use rpe as an integer 1-10 when "
            "provided, otherwise null. Use short lowercase strings for legs and pain when "
            "provided, otherwise null. Use notes for useful extra context, otherwise null. "
            "Do not invent fields. If the message is a normal coaching question or command, "
            "set is_feedback false and all other fields null."
        ),
        "input": message,
        "temperature": 0,
        "max_output_tokens": 200,
    }
    response = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
    text = _extract_output_text(response)
    if not text:
        raise RuntimeError("OpenAI response did not include feedback JSON.")
    return _clean_normalized_feedback(_parse_json_object(text))


def resolve_pending_question(
    *,
    question: str,
    response: str,
    kind: str,
) -> dict[str, Any]:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to resolve pending questions.")

    payload = {
        "model": os.environ.get("OPENAI_INTERACTION_MODEL")
        or os.environ.get("OPENAI_FEEDBACK_MODEL")
        or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "instructions": (
            "Decide whether the athlete's latest message answers the coach's pending "
            "question. Return only JSON with keys answers_question, kind, confidence, "
            "extracted. answers_question is true only when the response directly answers "
            "the pending question, even tersely. confidence is a number from 0 to 1. kind "
            "must echo the provided kind. For kind post_run_feedback, extracted must use "
            "keys is_feedback, rpe, legs, pain, notes with the same meanings as a post-run "
            "feel check: rpe is integer 1-10 when provided; legs, pain, and notes are short "
            "lowercase strings or null. If the response asks a new coaching question, gives "
            "an unrelated command, or does not answer the pending question, set "
            "answers_question false and extracted to an empty object. Do not invent values."
        ),
        "input": json.dumps(
            {
                "kind": kind,
                "coach_question": question,
                "athlete_response": response,
            }
        ),
        "temperature": 0,
        "max_output_tokens": 250,
    }
    openai_response = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
    text = _extract_output_text(openai_response)
    if not text:
        raise RuntimeError("OpenAI response did not include pending-question JSON.")
    return _clean_pending_question_resolution(_parse_json_object(text), fallback_kind=kind)


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
        elif call.get("name") == "update_weekly_plan_days":
            output = _execute_update_weekly_plan_days_tool(call)
        elif call.get("name") == "save_weekly_plan":
            output = _execute_save_weekly_plan_tool(call)
        elif call.get("name") == "save_race_result":
            output = _execute_save_race_result_tool(call)
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
    }
    if "max_output_tokens" in original_payload:
        followup_payload["max_output_tokens"] = original_payload["max_output_tokens"]
    if "temperature" in original_payload:
        followup_payload["temperature"] = original_payload["temperature"]
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
    week_start = _tool_argument(call, "week_start") or None
    plan = _clean_saved_weekly_plan(plan)
    result = save_weekly_plan(plan, week_start=week_start)
    saved_week_start = result.get("week_start", "") if isinstance(result, dict) else ""
    return _tool_output(
        call["call_id"],
        {
            "saved": True,
            "week_start": saved_week_start,
            "saved_plan": plan,
            "receipt": "Saved weekly plan:\n" + plan,
        },
    )


def _execute_update_weekly_plan_days_tool(call: dict[str, Any]) -> dict[str, str] | None:
    arguments = _tool_arguments(call)
    if arguments is None:
        return None
    updates = _weekly_plan_day_updates(arguments.get("updates"))
    if not updates:
        return None
    updates = {
        day: _clean_saved_weekly_plan_line(f"{day}: {workout}").split(None, 1)[1]
        for day, workout in updates.items()
    }
    result = update_weekly_plan_days(updates)
    saved_plan = result.get("text", "")
    changed_days = _saved_plan_lines_for_days(saved_plan, updates.keys())
    receipt = "Saved plan changes: " + "; ".join(changed_days)
    return _tool_output(
        call["call_id"],
        {
            "saved": True,
            "changed_days": changed_days,
            "saved_plan": saved_plan,
            "receipt": receipt,
        },
    )


def _execute_save_race_result_tool(call: dict[str, Any]) -> dict[str, str] | None:
    arguments = _tool_arguments(call)
    if arguments is None:
        return None
    result = save_race_result(
        race_name=str(arguments.get("race_name") or ""),
        race_date=str(arguments.get("race_date") or ""),
        distance=str(arguments.get("distance") or ""),
        time=str(arguments.get("time") or ""),
        source=str(arguments.get("source") or "athlete"),
    )
    return _tool_output(call["call_id"], {"saved": True, "result": result})


def _clean_saved_weekly_plan(plan: str) -> str:
    return "\n".join(_clean_saved_weekly_plan_line(line) for line in plan.strip().splitlines())


def _clean_saved_weekly_plan_line(line: str) -> str:
    stripped = line.strip()
    match = re.match(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b([,:-]?\s*)(.*)$",
        stripped,
        flags=re.IGNORECASE,
    )
    if not match:
        return stripped

    day = match.group(1).capitalize()
    workout = match.group(3).strip()
    cleaned = re.sub(
        r"^track\s+workout"
        r"(?:\s+for\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*\d{1,2}/\d{1,2})?"
        r"(?:\s+at\s+[^:;]+)?"
        r"\s*[:;-]\s*",
        "",
        workout,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"^.*?\btrack\s+workout\s*[:;-]\s*",
        "",
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"\bat\s+Underhill\s+Sports\s+Complex\b[,:;-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    if cleaned == workout:
        return stripped
    return f"{day}: {cleaned}"


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


def _weekly_plan_day_updates(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(day): str(workout) for day, workout in value.items()}
    if not isinstance(value, list):
        return {}
    updates: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        day = item.get("day")
        workout = item.get("workout")
        if isinstance(day, str) and isinstance(workout, str):
            updates[day] = workout
    return updates


def _saved_plan_lines_for_days(plan_text: str, days: Any) -> list[str]:
    wanted = {str(day).strip().lower() for day in days}
    lines: list[str] = []
    for raw_line in plan_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z]+)\b", line)
        if match and match.group(1).lower() in wanted:
            lines.append(line)
    return lines


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
    if response.get("status") == "incomplete" or response.get("incomplete_details"):
        reason = _incomplete_reason(response)
        raise RuntimeError(f"OpenAI response was incomplete: {reason}")

    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Response was not valid JSON: {text!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Response JSON must be an object: {text!r}")
    return parsed


def _clean_normalized_feedback(parsed: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"is_feedback": bool(parsed.get("is_feedback"))}
    rpe = parsed.get("rpe")
    result["rpe"] = rpe if isinstance(rpe, int) and 1 <= rpe <= 10 else None
    for key in ("legs", "pain", "notes"):
        value = parsed.get(key)
        result[key] = value.strip().lower() if isinstance(value, str) and value.strip() else None
    if not result["is_feedback"]:
        result.update({"rpe": None, "legs": None, "pain": None, "notes": None})
    return result


def _clean_pending_question_resolution(
    parsed: dict[str, Any],
    *,
    fallback_kind: str,
) -> dict[str, Any]:
    answers_question = bool(parsed.get("answers_question"))
    kind = parsed.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        kind = fallback_kind
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 1.0 if answers_question else 0.0
    confidence = max(0.0, min(1.0, float(confidence)))
    extracted = parsed.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}
    if kind == "post_run_feedback" and answers_question:
        extracted = _clean_normalized_feedback({**extracted, "is_feedback": True})
    elif not answers_question:
        extracted = {}
    return {
        "answers_question": answers_question,
        "kind": kind,
        "confidence": confidence,
        "extracted": extracted,
    }


def _incomplete_reason(response: dict[str, Any]) -> str:
    details = response.get("incomplete_details")
    if isinstance(details, dict):
        reason = details.get("reason")
        if reason:
            return str(reason)
    return "unknown reason"


def _fallback_reply(message: str, training_summary: str) -> str:
    return (
        "I can chat as your coach once OPENAI_API_KEY is set. For now, here is the current "
        "training readout I can see from Strava:\n\n"
        f"{training_summary}\n\n"
        "Rule of thumb for this question: keep the next run easy unless the last few days have "
        "felt fresh, and add volume gradually before adding intensity."
    )


def _image_data_url(image_bytes: bytes, mime_type: str) -> str:
    safe_mime_type = mime_type if mime_type.startswith("image/") else "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{safe_mime_type};base64,{encoded}"
