# Roadmap

This is a lightweight project board for work that would make the coach easier to
extend, debug, and trust. Keep it small: promote items only when they solve a real
problem we have seen. This is the result of the robot and I brainstorming.

## Backlog

### Agent Context Debug View

Why: When the coach gives a strange answer, the fastest debug path is seeing the
exact context it received: plan, goal, notes, reflection, Garmin, and Strava.
This should be an on-demand debugging command, not automatic logging.

Shape:

```bash
python -m running_agent debug-context "How's my recovery?"
```

The command should assemble the same context that a normal coach reply would use,
print it in readable sections, and stop before calling OpenAI. It should show the
user message, tools-enabled setting, training summary, recent runs, matched weekly
plan, goal, coaching notes, private reflection, Garmin context, and any obvious
freshness metadata.

Done when: A CLI or REPL command can print the assembled context for a sample
message without calling the model, and the output is useful enough to explain why
the coach might have answered the way it did.

### Scheduled Message Preview

Why: Morning, evening, and weekly messages are hard to tune if the only way to
see them is to wait for the scheduler or write one-off Python snippets.

Shape:

```bash
python -m running_agent preview morning
python -m running_agent preview evening --date 2026-06-05
python -m running_agent preview weekly --date 2026-06-07
```

The command should run the same generation path as the scheduler, but print the
message instead of sending it. It should support an optional date so we can test
edge cases like yesterday's evening message, a Sunday weekly message, or a race
weekend. It should make clear whether tools are disabled, whether the message
would normally be skipped, and what data sources were used.

Done when: There are simple preview commands for morning, evening, and weekly
messages, with an optional date, and they do not mutate scheduler state or send
Telegram messages.

### Reflection Lifecycle

Why: Reflections can make automated coaching more strategic if they are refreshed
on a predictable cadence. A daily reflection can reassess recovery, recent
training, goal progress, and the next concrete training emphasis without trying
to react to every single run.

Shape:

- Refresh the coach reflection once per day from recent Strava runs, Garmin
  context, the saved plan, coaching notes, and the overall goal.
- Keep the saved reflection compact and useful to the model: current capacity,
  goal confidence, next concrete progression, limiter, and watch items.
- Treat reflection as strategic background, not permission to override the saved
  weekly plan.

Done when: The scheduler refreshes reflection once per day, avoids duplicate
updates for the same day, and stores a concise thesis that improves later
coaching messages.

### Coach Event Logging

Why: When the coach gives a strange answer or misses a scheduled behavior, we
need a compact local trail of what happened: input, output, scheduler decisions,
tool calls, data refreshes, and errors.

Shape:

- Write structured JSONL events under `.data/`.
- Log inbound messages, outbound replies, scheduled trigger and skip decisions,
  model calls, tool calls, durable state changes, data refreshes, fallbacks, and
  errors.
- For tool calls that change state, include the tool name and saved value.
- Keep raw API payloads out of the default log.
- Consider a debug mode or separate context log for full assembled prompt/context
  snapshots.

Done when: A weird coach answer can be debugged from local logs without guessing
whether the issue was context, tool use, scheduler state, stale data, or model
behavior.

## Icebox

### State Mutation Guardrails

Why: Model tools that write memories, goals, and plans are powerful, but they
should only mutate durable state when the athlete clearly intends it.

Done when: Plan, goal, and memory tool instructions all distinguish explicit
state updates from brainstorming, examples, and casual discussion.

### Local Activity Store Health

Why: The Strava local store is useful, but it needs clearer freshness and missing
detail signals so bad answers are easier to trace.

Done when: A command reports last sync time, activity count, detail count, missing
details, and any obvious repair action.

### Manual Prompt Evaluation Set

Why: A small set of realistic conversations would help compare models and catch
regressions in tone, tool use, and state mutation behavior.

Done when: There are fixtures with user messages, context, expected behavior, and
a command that generates outputs for manual review.

### Data Freshness Model

Why: Garmin, Strava, plans, goals, notes, and reflections all have different
freshness rules. Making that explicit would reduce confusing answers.

Done when: The agent can explain what data is live, cached, local-only, or stale
for a given interaction.

### Automated Prompt Grading

Why: Useful eventually, but likely too much ceremony before we have a strong
manual evaluation set.

Done when: Reconsider only after manual prompt examples start catching real
regressions.
