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

### Historical Weekly Plan Context

Why: Weekly reviews can get confused if next week's plan is saved before the
current week is reviewed. The coach should not compare a completed week against
a future plan, and it should preserve enough plan context to judge missed or
changed workouts accurately.

Done when: Weekly reviews use a plan snapshot keyed to the reviewed week when
one exists, use the target-week plan only for forward guidance, and clearly say
when no saved plan exists for the completed week.

## Icebox

### Memory Mutation Guardrails

Why: Goal, plan, and race-result writes now have focused eval coverage. Memory
notes are still broader and could be over-saved if the model treats casual
conversation as durable preference.

Done when: Memory tool instructions and evals distinguish durable athlete
preferences or constraints from brainstorming, examples, one-off comments, and
ordinary coaching conversation.
