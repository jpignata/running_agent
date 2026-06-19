from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from running_agent.post_run_feedback import (
    append_post_run_feedback,
    clean_post_run_feedback,
    post_run_feedback_context,
    read_post_run_feedback,
)


class PostRunFeedbackTest(unittest.TestCase):
    def test_clean_post_run_feedback_preserves_raw_and_normalized_fields(self) -> None:
        feedback = clean_post_run_feedback(
            "Felt like 8, heavy legs, no pain",
            {"rpe": 8, "legs": "Heavy", "pain": "No", "notes": None},
        )

        self.assertEqual(
            feedback,
            {
                "raw": "Felt like 8, heavy legs, no pain",
                "rpe": 8,
                "legs": "heavy",
                "pain": "no",
            },
        )

    def test_clean_post_run_feedback_drops_invalid_fields(self) -> None:
        feedback = clean_post_run_feedback(
            "not really feedback",
            {"rpe": 14, "legs": "", "pain": None, "notes": "  "},
        )

        self.assertEqual(feedback, {"raw": "not really feedback"})

    def test_clean_post_run_feedback_normalizes_no_pain_phrase(self) -> None:
        feedback = clean_post_run_feedback(
            "RPE 3, legs normal, no pain, skipped the strides",
            {
                "rpe": 3,
                "legs": "normal",
                "pain": "no pain",
                "notes": "skipped the strides",
            },
        )

        self.assertEqual(feedback["pain"], "no")

    def test_append_post_run_feedback_stores_private_jsonl(self) -> None:
        path = _temp_path()

        entry = append_post_run_feedback(
            "RPE 8, legs sore, pain mild",
            normalized={"rpe": 8, "legs": "sore", "pain": "mild"},
            activity_id=123,
            run_date="2026-06-19",
            path=path,
        )

        self.assertEqual(entry["type"], "post_run_feedback")
        self.assertEqual(entry["activity_id"], 123)
        self.assertEqual(entry["run_date"], "2026-06-19")
        self.assertEqual(entry["rpe"], 8)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(read_post_run_feedback(path)[0]["rpe"], 8)

    def test_append_post_run_feedback_falls_back_to_raw_note(self) -> None:
        path = _temp_path()

        entry = append_post_run_feedback("Felt weird late", run_date="2026-06-19", path=path)

        self.assertEqual(entry["raw"], "Felt weird late")
        self.assertEqual(entry["notes"], "felt weird late")

    def test_post_run_feedback_context_formats_recent_entries(self) -> None:
        path = _temp_path()
        append_post_run_feedback(
            "RPE 5, legs fresh",
            normalized={"rpe": 5, "legs": "fresh"},
            run_date="2026-06-18",
            path=path,
        )
        append_post_run_feedback(
            "RPE 7, legs heavy, pain none, notes controlled",
            normalized={"rpe": 7, "legs": "heavy", "pain": "none", "notes": "controlled"},
            run_date="2026-06-19",
            path=path,
        )

        context = post_run_feedback_context(path)

        self.assertIn("Recent post-run feedback:", context)
        self.assertIn("2026-06-19; RPE 7; legs heavy; pain no; controlled", context)


def _temp_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=True)
    path = Path(handle.name)
    handle.close()
    return path


if __name__ == "__main__":
    unittest.main()
