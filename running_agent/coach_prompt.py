from __future__ import annotations

from .athlete_profile import athlete_profile_context
from .coach_reflection import coach_reflection_context
from .coach_time import coach_now
from .coaching_guidance import (
    COACHING_STANCE_RUBRIC,
    GARMIN_COACHING_RUBRIC,
    TRAINING_PROGRESSION_RUBRIC,
)

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
        "Return today's live Garmin readiness context, including readiness, sleep, naps, HRV, "
        "stress, resting HR, Body Battery, and athlete baseline ranges from cached completed days when "
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
        "Return recent Garmin recovery trend context from cached completed days, including nap "
        "patterns when available. Use this when "
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

COACHING_TOOLS = [
    REMEMBER_NOTE_TOOL,
    UPDATE_GOAL_TOOL,
    SAVE_WEEKLY_PLAN_TOOL,
    QUERY_LOCAL_RUNS_TOOL,
    GET_LOCAL_RUN_DETAILS_TOOL,
    GET_GARMIN_READINESS_TOOL,
    GET_GARMIN_TREND_TOOL,
]

COACHING_INSTRUCTIONS = (
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
    "rather than telling the athlete to do it. Do not claim the athlete completed a run "
    "today unless the recent Strava context explicitly says a run is recorded today. A "
    "weekly plan line is not evidence that a workout was completed. Avoid vague status "
    "labels like 'usable'; "
    "say concretely whether the metrics look steady, better than baseline, worse than "
    "baseline, mixed, or concerning. "
    "Garmin readiness, Body Battery, HRV, stress, sleep, naps, resting HR, and VO2 max are "
    "context to interpret alongside the plan, recent workload, and athlete-specific "
    "profile; do not let one generic Garmin label override the training plan by itself. "
    "When the athlete asks about Garmin readiness, recovery, sleep, naps, HRV, stress, resting "
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
)


def build_coaching_payload(
    *,
    model: str,
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
) -> dict:
    payload = {
        "model": model,
        "instructions": COACHING_INSTRUCTIONS,
        "input": build_coaching_input(
            message=message,
            training_summary=training_summary,
            recent_runs=recent_runs,
            weekly_plan=weekly_plan,
            training_goal=training_goal,
            coach_log=coach_log,
            garmin_context=garmin_context,
            conversation=conversation,
            include_coach_reflection=include_coach_reflection,
        ),
        "max_output_tokens": max_output_tokens,
    }
    if tools_enabled:
        payload["tools"] = COACHING_TOOLS
        payload["tool_choice"] = "auto"
    return payload


def build_coaching_input(
    *,
    message: str,
    training_summary: str,
    recent_runs: str,
    weekly_plan: str | None = None,
    training_goal: str | None = None,
    coach_log: str | None = None,
    garmin_context: str | None = None,
    conversation: list[dict[str, str]] | None = None,
    include_coach_reflection: bool = True,
) -> str:
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
    return "\n".join(prompt_parts)
