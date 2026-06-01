from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from running_agent.coach_agent import CoachAgent


class CoachAgentTest(unittest.TestCase):
    def test_handle_message_returns_replies_without_transport(self) -> None:
        agent = CoachAgent(strava_client=_FakeStrava())

        self.assertEqual(agent.handle_message("/ping"), ["Pong!"])

    @patch("running_agent.coach_agent.coach_now", return_value=datetime(2026, 6, 1, 4, 0))
    def test_tick_returns_messages_without_transport(self, _coach_now) -> None:
        state: dict = {}
        saves = []
        agent = CoachAgent(
            strava_client=_FakeStrava(),
            state=state,
            save_state=lambda: saves.append(dict(state)),
        )

        self.assertEqual(agent.tick(), [])
        self.assertEqual(state["seen_activity_ids"], [])
        self.assertEqual(saves, [{"seen_activity_ids": []}])


class _FakeStrava:
    def recent_activities(self, days: int) -> list[dict]:
        return []


if __name__ == "__main__":
    unittest.main()
