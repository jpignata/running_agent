from __future__ import annotations

from .athlete_profile import athlete_profile_context
from .coach_reflection import coach_reflection_context
from .coach_time import coach_now
from .coaching_guidance import (
    COACHING_STANCE_RUBRIC,
    DANIELS_TRAINING_RUBRIC,
    GARMIN_COACHING_RUBRIC,
    RPE_COACHING_RUBRIC,
    TRAINING_PROGRESSION_RUBRIC,
    coaching_philosophy_context,
)
from .pace_calibration import pace_calibration_context
from .race_results import race_results_context
from .run_memory import run_memory_context

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
        "existing goal details and incorporates the new information. If the athlete removes, "
        "drops, eliminates, pauses, or deprioritizes a previous goal, omit that removed goal "
        "entirely from the saved statement; do not save meta-language like 'remove the 5K goal', "
        "'5K goal removed', or 'no longer targeting the 5K'. Do not use this for ordinary workout "
        "preferences; use remember_coaching_note for those."
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
        "shares a day-by-day or week-long schedule that appears to be their actual plan, even if "
        "they do not use words like save, set, or update. Treat natural messages like 'next week "
        "is Mon easy, Tue workout...', 'this week: Monday 5, Wednesday 6x400...', 'here is my "
        "plan for next week', 'save this as my plan', 'move today's run to tomorrow', "
        "'make today rest and tomorrow 10', or 'that is the plan' as save intent. Do "
        "not use this when the athlete asks for a suggested, possible, hypothetical, or example "
        "plan, such as 'what might next week look like?', 'what could next week look like if...', "
        "'what should I do next week?', or 'suggest a plan'. Convert saved "
        "plans into clear plain text with one line for each planned day. When applying a partial "
        "edit to the current plan, rewrite and save the full revised week, preserving unchanged "
        "days and adding missing affected days when necessary. Preserve runner shorthand such as "
        "'2mi WU, 6x400m, CD'. When the athlete says this week or next week, resolve the "
        "Monday week_start date from the current local date and include it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": (
                    "The complete weekly plan text to save, ideally with one line per planned day."
                ),
            },
            "week_start": {
                "type": "string",
                "description": (
                    "Monday date for the plan week in YYYY-MM-DD format, or empty if unknown."
                ),
            },
        },
        "required": ["plan", "week_start"],
        "additionalProperties": False,
    },
    "strict": True,
}
UPDATE_WEEKLY_PLAN_DAYS_TOOL = {
    "type": "function",
    "name": "update_weekly_plan_days",
    "description": (
        "Apply one or more day-level edits to the current saved weekly plan while preserving "
        "unchanged days. Use this for partial plan edits such as moving today's run to tomorrow, "
        "making today rest, changing Saturday to 10 miles, swapping two days, or replacing one "
        "day's workout. Resolve relative dates like today and tomorrow from the current local "
        "date before calling. Pass one entry for each changed weekday, for example day "
        "Saturday workout rest, and day Sunday workout 10 miles."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "updates": {
                "type": "array",
                "description": "Changed weekday workouts.",
                "items": {
                    "type": "object",
                    "properties": {
                        "day": {
                            "type": "string",
                            "description": "Weekday name, such as Saturday or Sunday.",
                        },
                        "workout": {
                            "type": "string",
                            "description": "Revised workout for that day, such as rest or 10 miles.",
                        },
                    },
                    "required": ["day", "workout"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["updates"],
        "additionalProperties": False,
    },
    "strict": True,
}

SAVE_RACE_RESULT_TOOL = {
    "type": "function",
    "name": "save_race_result",
    "description": (
        "Save an official race result provided by the athlete for future coaching and VDOT "
        "calibration. Use this when the athlete gives a race name or clear race context plus "
        "a standard distance and finish time, especially when correcting GPS activity time or "
        "Strava best-effort data. Do not use this for workout reps or guessed race results."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "race_name": {
                "type": "string",
                "description": "Race name or concise identifying label.",
            },
            "race_date": {
                "type": "string",
                "description": "Race date in YYYY-MM-DD format if known.",
            },
            "distance": {
                "type": "string",
                "description": "Race distance such as 5K, 10K, half marathon, marathon, or 1 mile.",
            },
            "time": {
                "type": "string",
                "description": "Official finish time, such as 19:59 or 3:09:45.",
            },
            "source": {
                "type": "string",
                "description": "Where the result came from, usually athlete.",
            },
        },
        "required": ["race_name", "race_date", "distance", "time", "source"],
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
    UPDATE_WEEKLY_PLAN_DAYS_TOOL,
    SAVE_WEEKLY_PLAN_TOOL,
    SAVE_RACE_RESULT_TOOL,
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
    "When the athlete asks how many miles they ran this week, or asks for a day-by-day "
    "breakdown, use the current week mileage block from recent Strava context as the "
    "authoritative source. Do not combine it with future planned mileage, prior-week runs, "
    "or totals from recent conversation. If a weekday says no synced run recorded, treat "
    "that day as zero miles unless the athlete gives a correction. "
    "The current saved weekly plan takes precedence over the private coaching thesis for "
    "immediate workout advice. If the plan includes a race or deliberately easy day, do not "
    "recommend a harder or longer workout from the private thesis unless the athlete asks to "
    "revise the plan. Treat the private thesis as strategic background, not an instruction to "
    "override this week's plan. "
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
    "recovery data clearly warrants a training change. For strategic, educational, or "
    "long-range planning questions, answer at that level; do not pivot into today's "
    "workout, the current weekday, or the saved weekly plan unless the athlete asks what "
    "to do today or this week, asks whether to change the plan, or the current plan "
    "directly conflicts with the strategy being discussed. If recent Strava context shows "
    "today's planned workout has already been completed, discuss it in the past tense "
    "rather than telling the athlete to do it. Do not claim the athlete completed a run "
    "today unless the recent Strava context explicitly says a run is recorded today. A "
    "weekly plan line is not evidence that a workout was completed. Avoid vague status "
    "labels like 'usable'; "
    "When referring to the current local date's run or plan, say 'today' in the natural "
    "sentence before using the weekday name. Use weekday names mainly for past or future "
    "days, or when disambiguation helps. "
    "say concretely whether the metrics look steady, better than baseline, worse than "
    "baseline, mixed, or concerning. "
    "Garmin readiness, Body Battery, HRV, stress, sleep, naps, resting HR, and VO2 max are "
    "context to interpret alongside the plan, recent workload, and athlete-specific "
    "profile; do not let one generic Garmin label override the training plan by itself. "
    "When suggesting training or race paces, use any saved deterministic race-derived VDOT "
    "or pace calibration as the numeric starting point. Otherwise estimate a working VDOT from "
    "the athlete's recent evidence: representative races first, then controlled quality "
    "workouts, then longer-term aerobic patterns as sanity checks. Use published "
    "VDOT-equivalent paces from that working VDOT for Easy, Marathon, Threshold, Interval, "
    "and Repetition guidance. "
    "If the athlete asks for paces, VDOT, or pace calibration based on recent data or a recent "
    "race, call query_local_runs with races_only=true before answering unless a current pace "
    "calibration or the relevant race result is already present in the prompt. When you use a "
    "race result for pace calibration, cite the observed race distance and average pace in the "
    "reply so the athlete can audit the anchor. If the athlete gives or corrects an official "
    "race result, such as an official 5K time that differs from the full GPS activity or Strava "
    "best effort, call save_race_result before answering. Treat saved official race results as "
    "more authoritative than GPS activity duration or Strava best efforts for VDOT calibration. "
    "A race-result correction is not a training-goal update unless the athlete explicitly asks "
    "to change the goal. Do not claim an official race result was saved unless save_race_result "
    "was actually called. "
    "Do not let an aspirational goal pace inflate current training paces. If evidence conflicts, "
    "state the uncertainty and choose a conservative range. Do not make a same-distance or "
    "shorter-distance race pace much faster than an actual recent race unless broader evidence "
    "clearly supports a higher VDOT. When giving a same-distance race-pace range, anchor it at "
    "or very near the observed race average pace rather than making the fastest end substantially "
    "faster. As a rule of thumb, do not make the fastest end of a current same-distance "
    "race-pace range more than about 5 seconds per mile faster than a recent representative "
    "race unless you explain concrete evidence for discounting that race. For example, if a "
    "recent 5K-ish race averaged 6:22/mi, do not suggest current 5K pace of 6:10/mi or faster. "
    "Keep race-equivalent and training paces internally "
    "consistent. "
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
    "statement rather than saving only a fragment. When the athlete asks to remove, drop, "
    "eliminate, pause, or deprioritize part of the goal, remove it from the saved goal text "
    "entirely rather than saving text about the removal. After updating the goal, briefly "
    "acknowledge the change in the normal coaching reply. "
    "When the athlete shares a day-by-day or week-long schedule that appears to be their actual "
    "weekly training plan, call save_weekly_plan before answering. Do this even if they simply "
    "write the schedule naturally and do not explicitly say 'save this'. Treat messages like "
    "'next week is...', 'this week:', 'plan for the week:', and day-by-day lists with workout "
    "details as likely plan updates unless the athlete frames them as hypothetical, a question, "
    "or a request for your suggestion. Questions like 'what might next week look like', 'what "
    "could next week look like if...', or 'what should I do next week' are requests for advice, "
    "not plan-save requests. When the athlete asks to move, swap, replace, make today rest, make "
    "tomorrow a specific run, or otherwise edit only part of the current plan, call "
    "update_weekly_plan_days with the changed weekdays. Resolve relative dates like today and "
    "tomorrow from the current local date. For example, on Saturday, 'move today's run to "
    "tomorrow and make today rest' means update Saturday to rest and Sunday to the moved run. "
    "Do not say the plan was changed unless update_weekly_plan_days or save_weekly_plan was "
    "actually called. After a weekly plan tool call, ground the acknowledgement in the tool "
    "output. For a partial update, quote the returned changed_days or receipt exactly enough "
    "that the athlete can audit what was saved, for example 'Saved: Saturday rest; Sunday "
    "10 miles.' For a full weekly plan save, mention that the saved_plan was saved and include "
    "the concrete days if the athlete needs confirmation. Rewrite "
    "natural plan text into a complete plain-text weekly plan with one line per planned day, "
    "preserving runner shorthand. When saving a complete plan, include week_start as the Monday "
    "date for the plan week if the athlete says this week, next week, or gives enough dates to "
    "resolve it; otherwise pass an empty string. If the athlete asks for a "
    "suggested, possible, hypothetical, or example plan, answer with the suggestion but do not "
    "call save_weekly_plan unless they later explicitly approve it as the actual plan. After "
    "saving the plan, briefly acknowledge it in the normal coaching reply. "
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
    max_output_tokens: int | None = None,
    include_coach_reflection: bool = True,
    pace_calibration_text: str | None = None,
    temperature: float | None = None,
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
            pace_calibration_text=pace_calibration_text,
        ),
    }
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    if temperature is not None:
        payload["temperature"] = temperature
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
    athlete_profile_text: str | None = None,
    coach_reflection_text: str | None = None,
    coaching_philosophy_text: str | None = None,
    pace_calibration_text: str | None = None,
    run_memory_text: str | None = None,
) -> str:
    profile = (
        athlete_profile_text if athlete_profile_text is not None else athlete_profile_context()
    )
    philosophy = (
        coaching_philosophy_text
        if coaching_philosophy_text is not None
        else coaching_philosophy_context()
    )
    pace_calibration = (
        pace_calibration_text if pace_calibration_text is not None else pace_calibration_context()
    )
    race_results = race_results_context()
    run_memory = run_memory_text if run_memory_text is not None else run_memory_context()
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
        "Recent run memory:",
        run_memory,
        "",
        "Athlete-specific profile:",
        profile,
        "",
        race_results,
        "",
        pace_calibration,
        "",
        philosophy,
        "",
        COACHING_STANCE_RUBRIC,
        "",
        GARMIN_COACHING_RUBRIC,
        "",
        RPE_COACHING_RUBRIC,
        "",
        DANIELS_TRAINING_RUBRIC,
        "",
        TRAINING_PROGRESSION_RUBRIC,
    ]
    if include_coach_reflection:
        reflection = (
            coach_reflection_text
            if coach_reflection_text is not None
            else coach_reflection_context()
        )
        prompt_parts.extend(
            [
                "",
                "Coach's private current training thesis:",
                reflection,
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
