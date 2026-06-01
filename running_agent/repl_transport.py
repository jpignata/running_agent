from __future__ import annotations

from .coach_agent import CoachAgent


class ReplTransport:
    def __init__(self, coach: CoachAgent):
        self.coach = coach

    def run(self) -> None:
        print(
            "Running local coach REPL. Type /help for commands, /tick for due checks, /quit to exit."
        )
        while True:
            try:
                text = input("> ").strip()
            except EOFError:
                print()
                return
            except KeyboardInterrupt:
                print()
                return
            if not text:
                continue
            if text.lower() in {"/quit", "/exit"}:
                return

            self._print_messages(self.coach.handle_message(text))

    def _print_messages(self, messages: list[str]) -> None:
        for message in messages:
            print(message)
