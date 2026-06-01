from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .storage_paths import ATHLETE_PROFILE_PATH, prepare_parent

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


def append_coaching_preference(
    preference_text: str,
    path: Path = ATHLETE_PROFILE_PATH,
) -> str:
    preference_text = preference_text.strip()
    if not preference_text:
        raise RuntimeError("Coaching preference text cannot be empty.")

    profile = athlete_profile_context(path).rstrip()
    timestamp = datetime.now(timezone.utc).date().isoformat()
    profile = f"{profile}\n- {timestamp}: {preference_text}\n"
    prepare_parent(path)
    path.write_text(profile, encoding="utf-8")
    path.chmod(0o600)
    return profile.strip()
