# AGENTS.md

## Project

This is a local Telegram running coach bot. It reads completed runs from Strava,
stores a plain-text weekly plan and overall goal locally, and generates coaching
summaries.

## Principles

- Keep it dependency-light. Prefer Python stdlib unless there is a strong reason.
- Preserve privacy: never commit `.env`, Strava tokens, Telegram chat state, weekly
  plan, training goal, or exported Strava activity JSON.
- Favor simple deterministic heuristics before asking the model to infer everything.
- Telegram output should be plain text, not Markdown.
- Treat Strava, Telegram, and OpenAI clients as integration boundaries.

## Testing

- Do not call the network in tests.
- Use mocks or fakes for Strava, Telegram, and OpenAI boundaries.
- Keep tests focused on local parsing, formatting, classification, prompt/context
  assembly, and fallback behavior.

## Useful Commands

```bash
python -m unittest discover -s tests
python -m compileall running_agent tests
python -m running_agent run-detail 2026-05-27
python -m running_agent run-summary 2026-05-27
python -m running_agent telegram
```

## Data Model Notes

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

## Safety

- Do not delete or overwrite local state files unless explicitly asked.
- Do not commit personal data exports.
