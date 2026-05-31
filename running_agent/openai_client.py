from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .athlete_profile import athlete_profile_context
from .auth import load_env_file
from .coaching_guidance import GARMIN_COACHING_RUBRIC, TRAINING_PROGRESSION_RUBRIC

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.4-mini"


def coaching_reply(
    message: str,
    training_summary: str,
    recent_runs: str,
    weekly_plan: str | None = None,
    training_goal: str | None = None,
    coach_log: str | None = None,
    garmin_context: str | None = None,
    conversation: list[dict[str, str]] | None = None,
) -> str:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_reply(message, training_summary)

    prompt_parts = [
        "Current local date:",
        datetime.now().astimezone().strftime("%A, %B %-d, %Y"),
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
        GARMIN_COACHING_RUBRIC,
        "",
        TRAINING_PROGRESSION_RUBRIC,
    ]
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
            "context and weekly plan, be specific, concise, and encouraging. When a weekly plan "
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
            "Garmin readiness, Body Battery, HRV, stress, sleep, resting HR, and VO2 max are "
            "context to interpret alongside the plan, recent workload, and athlete-specific "
            "profile; do not let one generic Garmin label override the training plan by itself. "
            "Write in plain text for Telegram. Do not use Markdown formatting, including "
            "asterisk bold, headings, tables, or bullet symbols that require Markdown rendering. "
            "Do not diagnose injuries or give medical certainty; recommend rest or a clinician "
            "when pain, illness, or injury risk comes up."
        ),
        "input": "\n".join(prompt_parts),
        "max_output_tokens": 650,
    }
    response = _post_json(OPENAI_RESPONSES_URL, payload, api_key)
    text = _extract_output_text(response)
    if not text:
        raise RuntimeError("OpenAI response did not include text output.")
    return text.strip()


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
