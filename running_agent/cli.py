from __future__ import annotations

import argparse
import os
import time
import traceback

from .auth import build_authorization_url
from .strava_client import StravaClient
from .telegram_agent import TelegramRunningAgent


def main() -> int:
    try:
        return _main()
    except RuntimeError as error:
        print(f"Error: {error}")
        return 1


def _main() -> int:
    parser = argparse.ArgumentParser(prog="running-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("auth-url", help="Print the Strava OAuth authorization URL.")

    subparsers.add_parser("me", help="Verify Strava authentication and print athlete details.")

    exchange = subparsers.add_parser("exchange-code", help="Exchange an OAuth code for tokens.")
    exchange.add_argument("code", help="Code copied from the Strava OAuth redirect URL.")

    telegram = subparsers.add_parser(
        "telegram",
        help="Run the Telegram running coach and monitor Strava for new runs.",
    )
    telegram.add_argument("--days", type=int, default=21, help="Training lookback window in days.")
    telegram.add_argument(
        "--poll-seconds",
        type=int,
        default=300,
        help="How often to check Strava for newly synced runs.",
    )
    telegram.add_argument(
        "--restart-delay",
        type=int,
        default=10,
        help="Seconds to wait before restarting the Telegram coach after a crash.",
    )
    telegram.add_argument(
        "--no-restart",
        action="store_true",
        help="Disable the restart-on-crash supervisor.",
    )
    telegram.add_argument(
        "--debug-log",
        action="store_true",
        help="Print internal debug log events to stdout.",
    )

    repl = subparsers.add_parser(
        "repl",
        help="Chat with the running coach locally using the Telegram command handler.",
    )
    repl.add_argument("--days", type=int, default=21, help="Training lookback window in days.")
    repl.add_argument(
        "--debug-log",
        action="store_true",
        help="Print internal debug log events and rx/tx log lines.",
    )

    args = parser.parse_args()

    if args.command == "auth-url":
        print(build_authorization_url())
        return 0

    if args.command == "exchange-code":
        tokens = StravaClient.exchange_code(args.code)
        athlete = tokens.get("athlete", {})
        name = " ".join(
            part for part in [athlete.get("firstname"), athlete.get("lastname")] if part
        )
        print(f"Saved Strava tokens for {name or 'authenticated athlete'}.")
        return 0

    if args.command == "me":
        client = StravaClient()
        athlete = client.logged_in_athlete()
        name = " ".join(
            part for part in [athlete.get("firstname"), athlete.get("lastname")] if part
        )
        city = ", ".join(
            part
            for part in [
                athlete.get("city"),
                athlete.get("state"),
                athlete.get("country"),
            ]
            if part
        )
        print(f"Authenticated as: {name or 'Unknown athlete'}")
        if city:
            print(f"Location: {city}")
        return 0

    if args.command == "telegram":
        if args.debug_log:
            os.environ["RUNNING_AGENT_DEBUG_LOG"] = "1"
        if args.no_restart:
            agent = TelegramRunningAgent(poll_seconds=args.poll_seconds, lookback_days=args.days)
            agent.run_forever()
        else:
            _run_telegram_with_restarts(
                poll_seconds=args.poll_seconds,
                lookback_days=args.days,
                restart_delay=args.restart_delay,
            )
        return 0

    if args.command == "repl":
        if not args.debug_log:
            os.environ["RUNNING_AGENT_QUIET_LOG"] = "1"
        agent = TelegramRunningAgent(
            lookback_days=args.days,
            telegram_client=_ReplTelegramClient(),
            allowed_chat_id="repl",
        )
        _run_repl(agent)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_telegram_with_restarts(
    poll_seconds: int,
    lookback_days: int,
    restart_delay: int,
) -> None:
    print("Running Telegram coach with restart-on-crash enabled. Press Ctrl+C to stop.")
    while True:
        try:
            agent = TelegramRunningAgent(poll_seconds=poll_seconds, lookback_days=lookback_days)
            agent.run_forever()
        except KeyboardInterrupt:
            print("Stopping Telegram coach.")
            return
        except Exception as error:
            print(f"Telegram coach crashed: {error!r}")
            traceback.print_exc()
            print(f"Restarting in {restart_delay} seconds...")
            time.sleep(restart_delay)


class _ReplTelegramClient:
    def __init__(self):
        self.messages: list[str] = []

    def send_message(self, _chat_id: int | str, text: str) -> None:
        self.messages.append(text)


def _run_repl(agent: TelegramRunningAgent) -> None:
    print("Running local coach REPL. Type /help for commands, /quit to exit.")
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

        start = len(agent.telegram.messages)
        agent._handle_message("repl", text)
        for message in agent.telegram.messages[start:]:
            print(message)
