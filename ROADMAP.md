# Roadmap

This is a lightweight project board for work that would make the coach easier to
extend, debug, and trust. Keep it small: promote items only when they solve a real
problem we have seen. This is the result of the robot and I brainstorming.

## Backlog

### Local Activity Store Health

Why: The Strava local store is useful, but it needs clearer freshness and missing
detail signals so bad answers are easier to trace.

Done when: A command reports last sync time, activity count, detail count, missing
details, latest race-like activities, official saved race results, and any
obvious repair action.

### Data Freshness Model

Why: Garmin, Strava, plans, goals, official race results, notes, reflections,
and pace calibration all have different freshness rules. Making that explicit
would reduce confusing answers.

Done when: The agent can explain what data is live, cached, local-only, or stale
for a given interaction.

### Active Coaching Emphasis

Why: The coach reflection has a useful `Next emphasis`, but it is bundled into a
broader strategic thesis. The bot should have an explicit current coaching
priority that feels like a human coach remembering what we agreed to focus on
this week.

Done when: The agent can surface one current priority, such as "protect
Saturday's long run by keeping weekday mileage easy," use it only when relevant,
and update or retire it when the plan/week changes or the emphasis is satisfied.

### Reply Tone Calibration

Why: The bot can be technically right but emotionally off, such as framing a
volume increase as "only" because it is below long-term marathon needs. Coaching
should name progress and the remaining gap in the same breath.

Done when: Weekly reviews and post-run summaries consistently distinguish
progress versus the next requirement, avoid unsupported words like "only" or
"missed," and have eval coverage for progress-plus-gap framing.

### Scheduled Message Quality Evals

Why: Scheduled messages are some of the most visible coaching moments, but evals
mostly focus on conversational tool behavior. Morning check-ins, evening reports,
and weekly reviews need their own quality guardrails.

Done when: There are deterministic or judged eval cases for morning, evening, and
weekly scheduled messages covering brevity, complete sentences, plan/date
alignment, Garmin overreaction, and plain-text Telegram style.

### Telegram Conversation Polish

Why: Typing indicators made the bot feel more human. Telegram has more small
affordances that can make the coach feel present without changing the coaching
model.

Done when: Direct replies use Telegram reply-to-message where appropriate, slow
operations get lightweight acknowledgement only when they are expected to take a
while, and quick status commands stay instant and low-friction.

### Historical Weekly Plan Context

Why: Weekly reviews can get confused if next week's plan is saved before the
current week is reviewed. The coach should not compare a completed week against
a future plan, and it should preserve enough plan context to judge missed or
changed workouts accurately.

Observed failure: A Sunday weekly preview for the week ending 2026-06-14 used the
currently saved 2026-06-15 plan as if it described the completed week. That made
the coach critique execution against the wrong plan and mis-frame mileage.

Core distinction:

- The active plan answers "what should I do now or next?"
- Historical plan context answers "what did we think this week was supposed to be?"
- Weekly review needs both, but they must not be conflated.

Design question: should the plan itself become dated, or should we add history?

Option A - make the current plan dated more strictly:

- Keep `.data/weekly_plan.json` as the only plan file.
- Require every saved plan to have a `week_start`.
- Weekly review only compares against the current plan when its `week_start`
  matches the reviewed week.
- If the current plan points at a future week, review says no saved plan exists
  for the completed week.
- Pros: smallest change, easy to reason about, avoids wrong comparisons.
- Cons: once a new plan replaces the old one, missed/changed workouts from the
  prior week are unavailable except for partial coach-log run snapshots.

Option B - add weekly plan history:

- Keep `.data/weekly_plan.json` as the active/current plan.
- Add `.data/weekly_plan_history.json` keyed by Monday `week_start`.
- Every full plan save or partial day update writes a snapshot for that
  `week_start`.
- Weekly review loads the reviewed-week snapshot from history and loads the
  target-week plan separately for forward guidance.
- Pros: preserves the coach's memory of prior plans, supports accurate missed-day
  and over/under-plan review, lets the athlete save next week early.
- Cons: new state file and more edge cases around partial updates, missing
  `week_start`, corrections, and cleanup.

Option C - attach plan snapshots to activities / coach log only:

- Continue storing `planned_workout` on each completed run in `.data/coach_log.jsonl`.
- Use those entries for weekly review.
- Pros: already partly exists, strong evidence for completed run intent.
- Cons: cannot represent missed workouts, rest/cross-training days, or total
  planned mileage; not enough for reliable weekly reviews by itself.

Likely direction: Option B, but implement it in small steps so Option A's safety
guard lands first.

Granular implementation:

1. Add strict week matching in weekly review.
   - Use a reviewed-week plan only if `week_start == reviewed_week_start`.
   - Use the target-week plan only for next-week guidance.
   - If no reviewed-week plan exists, tell the model that explicitly.
   - Add tests where the current saved plan is for next week and must not be used
     to judge the completed week.

2. Add deterministic weekly-review facts.
   - Compute completed mileage for the reviewed Monday-Sunday window.
   - Estimate planned mileage from explicit plan miles when a matching plan exists.
   - Include planned/completed/delta only when the plan is for the reviewed week.
   - Tell the model not to use words like "only," "under plan," or "missed" unless
     those claims are supported by the deterministic facts.

3. Add `.data/weekly_plan_history.json`.
   - Suggested shape:
     `{ "plans": { "2026-06-08": { "week_start": "2026-06-08", "updated_at": "...", "text": "..." } } }`
   - Keep it ignored/private like the other `.data/` files.
   - On `save_weekly_plan`, write both current plan and history when `week_start`
     is known.
   - On `update_weekly_plan_days`, update the current plan and refresh the matching
     history snapshot.

4. Backfill gently from current state.
   - If `.data/weekly_plan.json` has a `week_start`, treat it as one history
     snapshot.
   - Do not try to infer old plans from conversation or Strava.
   - Existing coach-log run snapshots remain useful partial evidence.

5. Update weekly review prompt/context.
   - Provide separate fields/sections for:
     reviewed-week plan,
     reviewed-week deterministic facts,
     target-week plan,
     coach log.
   - Make the prompt say: if reviewed-week plan is missing, do not claim the
     athlete was over/under the plan; judge from completed runs and say plan
     comparison is unavailable.

6. Add tests and evals.
   - Unit tests for history save/update/read.
   - Weekly review test where reviewed-week plan and target-week plan differ.
   - Regression eval for "next week's plan saved early" so the review does not
     compare completed runs against a future plan.

Done when:

- Weekly reviews use a reviewed-week plan snapshot when one exists.
- Weekly reviews use the target-week plan only for forward guidance.
- The coach clearly says when no saved plan exists for the completed week.
- Planned mileage comparisons come from deterministic facts, not model inference.
- Updating next week's plan early no longer corrupts the review of the current week.

## Icebox

### Telegram Admin Commands

Why: The phone is the natural control surface for this local bot. Some safe
operational commands could reduce SSH trips, but admin features need tight
guardrails.

Done when: A small allowlisted command set can show service health, trigger safe
previews, or request diagnostics without exposing secrets, shell access, raw
tokens, or destructive actions.

### Plan Approval Workflow

Why: The model currently saves likely weekly plans automatically. That is handy,
but there are cases where it may be better to draft a normalized plan and ask for
confirmation before mutating state.

Done when: Ambiguous plan-like messages can produce a clear proposed saved plan
with a lightweight approve/cancel interaction, while unambiguous plan updates
remain fast.

### Memory Mutation Guardrails

Why: Goal, plan, and race-result writes now have focused eval coverage. Memory
notes are still broader and could be over-saved if the model treats casual
conversation as durable preference.

Done when: Memory tool instructions and evals distinguish durable athlete
preferences or constraints from brainstorming, examples, one-off comments, and
ordinary coaching conversation.
