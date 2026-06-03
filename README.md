# Running Agent

A system for automated running coaching toward race goals.

It uses training and recovery data from sources like Strava and Garmin to review workouts,
adjust advice, and suggest what to do next. An athlete interacts with the system via
Telegram through a conversational interface. The system also sends scheduled messages such
as after a workout to summarize the results.

Built with Codex.

## Details

### Runtime Behavior

When `python -m running_agent telegram` is running, the bot:

- Polls Telegram for chat messages and slash commands.
- Checks Strava on the configured interval for newly synced runs.
- Sends a natural post-run coaching note when a new run appears.
- Refreshes the Garmin snapshot cache once per day after 5:00am Eastern.
- Sends one morning workout check-in after 5:30am Eastern when today's saved plan has
  a workout and Strava does not already show a completed run for the day.
- Sends one integrated Sunday evening review plus next-week plan idea after 6:00pm
  Eastern.

### Coaching Context

The coach builds replies from local context instead of treating each message as isolated:

- Recent Strava runs, including detailed laps when they matter, such as workouts, races,
  and long runs.
- Synced local Strava activity history in `.data/strava/`, with compact run summaries
  and per-activity detail files for lap/split lookup.
- The saved weekly plan in `.data/weekly_plan.json`, parsed by weekday when possible.
- The saved training goal in `.data/training_goal.json`.
- Athlete-specific notes in `.data/athlete_profile.txt`.
- The local coach log in `.data/coach_log.jsonl`, which records planned-versus-completed
  run outcomes.
- Cached Garmin snapshots in `.data/garmin_snapshots.json`, including baseline ranges for
  sleep, resting heart rate, HRV, stress, Body Battery low, and training readiness.
- Short in-process conversation history while the bot is running.

## Setup

### Step 1: Connect Strava

Create a Strava API app at https://www.strava.com/settings/api.

Use `localhost` for the app's authorization callback domain while developing locally.

Copy the environment template:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
STRAVA_CLIENT_ID=your-client-id
STRAVA_CLIENT_SECRET=your-client-secret
STRAVA_REDIRECT_URI=http://localhost/exchange_token
```

Generate an authorization URL:

```bash
python -m running_agent auth-url
```

Open the URL, approve access, then copy the `code` query parameter from the redirect URL and exchange it:

```bash
python -m running_agent exchange-code YOUR_CODE
```

This writes `.strava_tokens.json`, which is ignored by git.

Verify the connection:

```bash
python -m running_agent me
```

Backfill local Strava run history so the coach can answer older activity questions and
lap/split questions without fetching Strava during the model tool call:

```bash
python -m running_agent sync-strava --days 365
```

### Step 2: Connect Garmin

Garmin Connect is optional, but it gives the coach recovery context for morning workout
check-ins. Add your Garmin credentials to `.env`:

```bash
GARMIN_EMAIL=you@example.com
GARMIN_PASSWORD=your-garmin-password
```

The first coaching request that uses Garmin may prompt for a Garmin MFA code. Garmin tokens
are cached under `~/.garminconnect`.

The Telegram process refreshes recent Garmin snapshots once per day after 5:00am Eastern
and stores them in `.data/garmin_snapshots.json`. Garmin commands and coaching prompts use
that local cache for daily context and athlete baseline ranges instead of refetching the
full baseline on every request.

### Step 3: Connect Telegram

Create a bot with Telegram's `@BotFather`, copy the bot token, and add it to `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456:your-telegram-bot-token
```

Optionally set `TELEGRAM_CHAT_ID` if you already know the chat ID. If you leave it blank,
the first Telegram chat to message the bot is saved in `.data/state.json`.

For natural coaching replies, add an OpenAI API key:

```bash
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-5.4-mini
```

Run the coach:

```bash
python -m running_agent telegram
```

The Telegram process restarts itself after crashes by default. This is intentionally simple:
if Telegram, Strava, or OpenAI times out, the command logs the traceback, waits 10 seconds,
and starts a fresh agent.

For debugging, run without the supervisor:

```bash
python -m running_agent telegram --no-restart
```

To print internal debug events in addition to received/sent message lines:

```bash
python -m running_agent telegram --debug-log
```

To test the coach locally without sending Telegram messages, use the REPL:

```bash
python -m running_agent repl
```

The REPL talks to the same coach agent as Telegram. Type `/help` to list chat commands,
`/tick` to run due scheduled checks, and `/quit` to exit. By default it hides rx/tx log
lines; add `--debug-log` to see them.

Then message the bot on Telegram. It supports:

- `/recent` - summarize recent Strava run training
- `/last` - send a workout summary for the latest Strava run
- `/run YYYY-MM-DD` - send a workout summary for a specific day
- `/suggestplan` - suggest a plan idea for next week
- `/plan` - show the current weekly plan
- `/setplan <plan>` - save this week's plan
- `/goal` - show the current overall training goal
- `/setgoal <goal>` - save your overall training goal
- `/preferences` - show remembered coaching notes and preferences
- `/preference <note>` - explicitly save a coaching note
- `/garmin` - show today's Garmin readiness context
- `/garminweek` - show recent Garmin recovery trend
- `/check` - check for newly synced Strava runs now
- `/tick` - run due scheduled checks now
- Any other message - chat with the coach using recent Strava context

The coach can also remember natural-language notes when chatting. For example, if you say
`remember that I prefer long runs on Saturday`, the model may call its local note-saving tool,
store that in `.data/athlete_profile.txt`, and use it in future coaching.

The same model-tool pattern is available for goals. If you say something like
`my main goal is Boston on Oct 12, ideally 3:10`, the model may rewrite the saved goal in
`.data/training_goal.json` so future coaching uses the updated target.

Weekly plans can also be saved through natural chat. If you say something like
`here is my plan for next week`, the model may rewrite it into the plain-text weekly plan
format and save it in `.data/weekly_plan.json`.

The Telegram process checks Strava every five minutes by default, sends a short coaching
note when a new run appears, sends one morning workout check-in after 5:30am Eastern when
today's weekly plan has a matched workout that has not already been completed, and sends
one Sunday evening review plus next-week plan idea after 6:00pm Eastern. It also refreshes
the Garmin snapshot cache once per day after 5:00am Eastern. Change the polling interval
with:

```bash
python -m running_agent telegram --poll-seconds 120 --days 28
```

When a new run syncs, the bot appends a compact local coach-log entry to `.data/coach_log.jsonl`
with the matched planned workout and completed run headline. This file is ignored by git and
used as context for future plan suggestions.

The same new-run check also stores the Strava summary and detailed activity JSON under
`.data/strava/`, so future chat questions can look up that run's laps and splits locally.

The morning check-in uses Garmin readiness context when configured, plus today's matched
plan, the last week of runs, the coach log, and your overall goal. If there is no workout
scheduled for the day or Strava already has a completed run for that date, the bot sends
nothing.

### Step 4: Add A Weekly Plan

Send the plan in Telegram or the local REPL so the coach can compare completed Strava runs
against what you intended to do:

```text
/setplan Mon 5 easy. Tue 6 x 800m. Wed rest. Thu 8 steady. Sat 14 long.
```

You can also use natural language, for example `here is my plan for next week...`; the model
may call its plan-saving tool and rewrite it into the saved weekly plan format.

### Step 5: Add An Overall Goal

Set the larger goal in Telegram or the local REPL so the coach can interpret workouts in
context:

```text
/setgoal Chicago Marathon on Oct 11, target 3:20, stay healthy.
```

You can also state the goal naturally, for example `my main goal is Chicago on Oct 11,
target 3:20`; the model may call its goal-update tool and rewrite the saved goal.

## Tests

Run unit tests:

```bash
python -m unittest discover -s tests
```
