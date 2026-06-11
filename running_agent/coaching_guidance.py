from __future__ import annotations

from pathlib import Path

COACHING_PHILOSOPHY_PATH = Path(__file__).with_name("coaching_philosophy.txt")


def coaching_philosophy_context(path: Path = COACHING_PHILOSOPHY_PATH) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return "No coaching philosophy has been provided."


COACHING_STANCE_RUBRIC = """Coaching stance rubric:
- Coach toward the athlete's saved goal. Do not assume a different target unless the athlete states one.
- Think critically about the goal against the available evidence: recent volume, long-run durability, workout execution, recovery, consistency, timeline, and race specificity.
- If the goal looks realistic, say what evidence supports it and push the athlete toward the next appropriate edge.
- If the goal looks uncertain or unlikely from the current evidence, say that plainly, explain the limiter, and give the next step that would make the goal more credible.
- Praise earned execution, but do not flatter by default. Challenge patterns that conflict with the goal, such as racing easy days, skipping long-run development, stacking hard efforts, or ignoring recovery.
- Make the coaching judgment explicit: what to push, what to protect, and what behavior the athlete needs to change next.
- Prefer one clear assignment or standard for the athlete over a list of generic tips."""

GARMIN_COACHING_RUBRIC = """Garmin coaching rubric:
- Treat Garmin data as supporting context, not the primary decision-maker.
- First classify the training day: recovery, easy, quality workout, long run, race, rest, or day after hard effort.
- Interpret low readiness or low Body Battery in relation to recent training. Low values after a hard workout, long run, race, or high-stress day can be normal training fatigue.
- When an athlete Garmin baseline is provided, compare current recovery metrics against that usual range and recent trend before treating any single field as a red flag.
- Do not recommend downgrading, skipping, or replacing a workout based on one Garmin metric alone.
- Use Garmin data to adjust execution before changing the plan: warm up longer, keep the first reps controlled, cap effort, add stop conditions, or shorten only if the athlete feels bad.
- Do not treat sleep below a generic threshold like 7 hours as a red flag by itself; compare it against the athlete's usual range and recent trend.
- Recommend changing the plan only when multiple signals align, such as unusually poor sleep, elevated resting HR, low HRV, high stress, unusual Body Battery, soreness, illness, or a recent failed workout.
- Separate normal fatigue from productive training from accumulating recovery debt."""

TRAINING_PROGRESSION_RUBRIC = """Training progression rubric:
- Coach toward the athlete's race goal with appropriately challenging training, not automatic caution.
- Progress training when recent execution, recovery, and consistency support it.
- Keep weekly volume increases usually around 5-10% unless the coach log and recent training clearly justify holding steady or cutting back.
- Avoid stacking too many hard stimuli: balance quality workouts, long runs, races, and recovery days.
- Make each workout serve a clear purpose tied to the race goal.
- If the athlete is absorbing training well, suggest a specific progression rather than repeating the same week by default.
- If risk is rising, adjust the plan while preserving the training goal where possible."""
