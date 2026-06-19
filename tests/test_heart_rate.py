from __future__ import annotations

import unittest

from running_agent.heart_rate import (
    format_heart_rate,
    heart_rate_percent,
    observed_max_heart_rate,
)


class HeartRateTest(unittest.TestCase):
    def test_observed_max_heart_rate_uses_activity_and_lap_maxes(self) -> None:
        max_hr = observed_max_heart_rate(
            [
                {"max_heartrate": 174},
                {"max_heartrate": 179, "laps": [{"max_heartrate": 181}]},
                {"max_heartrate": 500},
            ]
        )

        self.assertEqual(max_hr, 181)

    def test_heart_rate_percent_requires_reasonable_values(self) -> None:
        self.assertEqual(heart_rate_percent(144, 180), 80)
        self.assertIsNone(heart_rate_percent(181, 180))
        self.assertIsNone(heart_rate_percent(144, None))
        self.assertIsNone(heart_rate_percent(20, 180))

    def test_format_heart_rate_includes_percent_when_reference_is_available(self) -> None:
        self.assertEqual(format_heart_rate(141, 180), "141 bpm (78% max HR)")
        self.assertEqual(format_heart_rate(141, None), "141 bpm")
        self.assertEqual(format_heart_rate(None, 180), "n/a")


if __name__ == "__main__":
    unittest.main()
