from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.athlete_profile import (
    append_coaching_preference,
    athlete_profile_context,
)


class AthleteProfileTest(unittest.TestCase):
    def test_athlete_profile_uses_default_when_missing(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "missing-running-agent-athlete-profile.txt"
        if missing_path.exists():
            missing_path.unlink()

        context = athlete_profile_context(missing_path)

        self.assertIn("Body Battery below 40 can be normal", context)
        self.assertIn("Low Garmin readiness is expected after hard workouts", context)

    def test_athlete_profile_reads_local_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as handle:
            handle.write("Custom athlete note")
            handle.flush()

            context = athlete_profile_context(Path(handle.name))

        self.assertEqual(context, "Custom athlete note")

    def test_append_coaching_preference_adds_note_under_existing_profile(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as handle:
            path = Path(handle.name)
            handle.write("Athlete-specific coaching notes:\n- Existing profile")
            handle.flush()

            context = append_coaching_preference("I prefer effort-based workout guidance.", path)

        self.assertIn("- Existing profile", context)
        self.assertNotIn("User-stated coaching notes:", context)
        self.assertIn("I prefer effort-based workout guidance.", context)


if __name__ == "__main__":
    unittest.main()
