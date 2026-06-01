# Running Agent

A local system for automated running coaching toward race goals.

It uses training and recovery data from sources like Strava and Garmin to review workouts,
adjust advice, and suggest what to do next.

Built with Codex.

## Step 1: Connect Strava

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

## Step 2: Connect Garmin

Garmin Connect is optional, but it gives the coach recovery context for morning workout
check-ins. Add your Garmin credentials to `.env`:

```bash
GARMIN_EMAIL=you@example.com
GARMIN_PASSWORD=your-garmin-password
```

The first coaching request that uses Garmin may prompt for a Garmin MFA code. Garmin tokens
are cached under `~/.garminconnect`.

## Step 3: Connect Telegram

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

To test the Telegram-style chat flow locally without sending Telegram messages, use the REPL:

```bash
python -m running_agent repl
```

The REPL uses the same command handler as Telegram. Type `/help` to list chat commands and
`/quit` to exit. By default it hides rx/tx log lines; add `--debug-log` to see them.

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
one Sunday evening review plus next-week plan idea after 6:00pm Eastern. Change the polling
interval with:

```bash
python -m running_agent telegram --poll-seconds 120 --days 28
```

When a new run syncs, the bot appends a compact local coach-log entry to `.data/coach_log.jsonl`
with the matched planned workout and completed run headline. This file is ignored by git and
used as context for future plan suggestions.

The morning check-in uses Garmin readiness context when configured, plus today's matched
plan, the last week of runs, the coach log, and your overall goal. If there is no workout
scheduled for the day or Strava already has a completed run for that date, the bot sends
nothing.

## Step 4: Add A Weekly Plan

Send the plan in Telegram or the local REPL so the coach can compare completed Strava runs
against what you intended to do:

```text
/setplan Mon 5 easy. Tue 6 x 800m. Wed rest. Thu 8 steady. Sat 14 long.
```

You can also use natural language, for example `here is my plan for next week...`; the model
may call its plan-saving tool and rewrite it into the saved weekly plan format.

## Step 5: Add An Overall Goal

Set the larger goal in Telegram or the local REPL so the coach can interpret workouts in
context:

```text
/setgoal Chicago Marathon on Oct 11, target 3:20, stay healthy.
```

You can also state the goal naturally, for example `my main goal is Chicago on Oct 11,
target 3:20`; the model may call its goal-update tool and rewrite the saved goal.

## What The First Agent Checks

- Weekly mileage trend
- Longest run in the selected window
- Lap-by-lap distance, pace, moving time, elapsed time, and heart-rate context
- Easy versus harder effort split, estimated from heart rate if present
- Basic consistency notes for marathon training
- Telegram chat replies grounded in recent Strava runs
- Athlete-provided weekly plan context
- Athlete-provided overall training goal context
- Local coach log of planned-versus-completed runs
- Garmin readiness context for morning workout check-ins
- New-run monitoring with a short post-run coaching note
- Daily 5:30am Eastern workout check-ins for planned, not-yet-completed workout days
- Sunday evening weekly reviews and next-week plan suggestions after 6:00pm Eastern

## Tests

Run unit tests:

```bash
python -m unittest discover -s tests
```
