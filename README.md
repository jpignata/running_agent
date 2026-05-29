# Running Agent

A small local agent for reviewing marathon training from Strava workouts.

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

Fetch recent activities and print early feedback:

```bash
python -m running_agent recent --days 14
```

Print the latest Strava run:

```bash
python -m running_agent latest-run
python -m running_agent latest-run-detail
python -m running_agent run-detail 2026-05-27
python -m running_agent run-summary 2026-05-27
```

## Step 2: Connect Telegram

Create a bot with Telegram's `@BotFather`, copy the bot token, and add it to `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456:your-telegram-bot-token
```

Optionally set `TELEGRAM_CHAT_ID` if you already know the chat ID. If you leave it blank,
the first Telegram chat to message the bot is saved in `.running_agent_state.json`.

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

Then message the bot on Telegram. It supports:

- `/recent` - summarize recent Strava run training
- `/last` - send a workout summary for the latest Strava run
- `/run YYYY-MM-DD` - send a workout summary for a specific day
- `/plan` - show the current weekly plan
- `/setplan <plan>` - save this week's plan
- `/goal` - show the current overall training goal
- `/setgoal <goal>` - save your overall training goal
- `/check` - check for newly synced Strava runs now
- Any other message - chat with the coach using recent Strava context

The Telegram process checks Strava every five minutes by default and sends a short coaching
note when a new run appears. Change that interval with:

```bash
python -m running_agent telegram --poll-seconds 120 --days 28
```

For a quick demo without waiting for the bot loop, send a latest-run summary directly:

```bash
python -m running_agent send-last-run
python -m running_agent send-run-summary 2026-05-27
```

## Step 3: Add A Weekly Plan

Save a plain-text weekly plan so the coach can compare completed Strava runs against what
you intended to do:

```bash
python -m running_agent set-plan weekly-plan.txt
python -m running_agent show-plan
```

You can also paste the plan into Telegram:

```text
/setplan Mon 5 easy. Tue 6 x 800m. Wed rest. Thu 8 steady. Sat 14 long.
```

## Step 4: Add An Overall Goal

Save the larger goal so the coach can interpret workouts in context:

```bash
python -m running_agent set-goal "Chicago Marathon on Oct 11, target 3:20, stay healthy."
python -m running_agent show-goal
```

Or set it in Telegram:

```text
/setgoal Chicago Marathon on Oct 11, target 3:20, stay healthy.
```

## What The First Agent Checks

- Weekly mileage trend
- Longest run in the selected window
- Lap-by-lap distance, pace, moving time, elapsed time, and heart-rate context
- Easy versus harder effort split, estimated from heart rate if present
- Basic consistency notes for marathon training
- Telegram chat replies grounded in recent Strava runs
- Athlete-provided weekly plan context
- Athlete-provided overall training goal context
- New-run monitoring with a short post-run coaching note

## Tests

Run unit tests:

```bash
python -m unittest discover -s tests
```
