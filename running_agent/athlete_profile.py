from __future__ import annotations

from pathlib import Path

ATHLETE_PROFILE_PATH = Path(".athlete_profile.txt")

DEFAULT_ATHLETE_PROFILE = """Athlete-specific coaching notes:
- Body Battery below 40 can be normal for this athlete and is not automatically concerning.
- Low Garmin readiness is expected after hard workouts, long runs, races, or high-stress days.
- Prefer not to skip quality work unless several fatigue signals align with the training context.
"""


def athlete_profile_context(path: Path = ATHLETE_PROFILE_PATH) -> str:
    if not path.exists():
        return DEFAULT_ATHLETE_PROFILE.strip()

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return DEFAULT_ATHLETE_PROFILE.strip()
    return text
