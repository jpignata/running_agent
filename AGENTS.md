# AGENTS.md

## Project

This is a local Telegram running coach bot. It reads completed runs from Strava,
stores a plain-text weekly plan and overall goal locally, and generates coaching
summaries.

## Principles

- Keep it dependency-light. Prefer Python stdlib unless there is a strong reason.
- Preserve privacy: never commit `.env`, Strava tokens, `.data/`, or exported
  Strava activity JSON.
- Favor simple deterministic heuristics before asking the model to infer everything.
- Telegram output should be plain text, not Markdown.
- Treat Strava, Telegram, and OpenAI clients as integration boundaries.
- Logs should go to stdout only; do not add disk event logs.
- Scheduled coaching behavior uses `America/New_York`, not the host timezone.

## Testing

- Do not call the network in tests.
- Use mocks or fakes for Strava, Telegram, and OpenAI boundaries.
- Add or update tests for local logic changes, especially parsing, formatting,
  classification, prompt/context assembly, and fallback behavior.
- Keep tests focused on local parsing, formatting, classification, prompt/context
  assembly, and fallback behavior.
- Keep tests fast and dependency-free. If there's a strong reason, let's discuss first.

## Git Workflow

- Favor small, focused, atomic commits. Split unrelated documentation, prompt, tool, and
  behavior changes into separate commits when practical.

## Setup

- Activate the project virtualenv before running commands:

```bash
source .venv/bin/activate
```

- After activation, use `python` for project commands. If `python` is not available,
  fix the shell/virtualenv setup rather than changing project docs or examples to
  use `.venv/bin/python` or `python3`.

## Useful Commands

```bash
python -m unittest discover -s tests
python -m compileall running_agent tests
python -m running_agent auth-url
python -m running_agent me
python -m running_agent repl
python -m running_agent telegram
```

## Data Model Notes

- Non-secret local app data lives under `.data/`:
  - `.data/state.json`
  - `.data/weekly_plan.json`
  - `.data/training_goal.json`
  - `.data/athlete_profile.txt`
  - `.data/coach_log.jsonl`
  - `.data/garmin_snapshots.json`
- Keep `.env` and `.strava_tokens.json` separate from `.data/`.
- Weekly plans are plain text, but parsed by weekday.
- Races should be explicitly marked in the weekly plan, for example `Saturday 5K race`.
- Structured workouts can be natural runner shorthand, for example
  `2mi WU, 4x1200m, CD`.
- The classifier should trust matched plan intent first, then lap patterns.

## Prompting Notes

- Include matched plan day, workout classification, goal, and detailed lap context for
  run summaries.
- Lap data matters most for structured workouts, tempos, races, and quality days.
- For easy runs, avoid over-analyzing laps.
- Telegram messages should feel like natural, coherent coach texts rather than
  report-style output.
- Combine related coaching context into one readable message instead of stitching
  together separate sections or model outputs.
- Use model tools for remembering coaching notes, updating goals, and saving weekly
  plans; do not add brittle hard-coded phrase detection unless explicitly requested.

## Safety

- Do not delete or overwrite local state files unless explicitly asked.
- Do not commit personal data exports.
