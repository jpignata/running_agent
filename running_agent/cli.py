from __future__ import annotations

import argparse
import os
from datetime import date

from .agent_state import load_agent_state, save_agent_state
from .auth import build_authorization_url
from .coach_agent import DEFAULT_LOOKBACK_DAYS, CoachAgent
from .coach_reflection import generate_coach_reflection
from .eval_runner import main as eval_runner_main
from .repl_transport import ReplTransport
from .run_memory import refresh_run_memory, run_memory_context, validate_run_memory
from .scheduled_preview import format_scheduled_preview, preview_scheduled_message
from .storage_paths import STATE_PATH
from .strava_client import StravaClient
from .strava_store import format_local_store_health, local_store_health
from .strava_sync import sync_strava_runs
from .systemd_service import boot_linger_hint, install_telegram_user_service
from .telegram_transport import TelegramTransport


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

    sync_strava = subparsers.add_parser(
        "sync-strava",
        help="Sync local Strava run summaries and detailed lap data.",
    )
    sync_strava.add_argument(
        "--days",
        type=int,
        default=365,
        help="How many days of Strava activities to sync.",
    )

    subparsers.add_parser(
        "strava-store-health",
        help="Report local Strava store freshness, completeness, and repair hints.",
    )

    run_memory = subparsers.add_parser(
        "run-memory",
        help="Refresh and print the local derived run-memory store.",
    )
    run_memory.add_argument(
        "--days",
        type=int,
        default=28,
        help="How many days of local runs to include.",
    )
    run_memory.add_argument(
        "--sync",
        action="store_true",
        help="Sync Strava runs before rebuilding run memory.",
    )
    run_memory.add_argument(
        "--validate",
        action="store_true",
        help="Check that rebuilt run memory reflects source feedback entries.",
    )

    reflect = subparsers.add_parser(
        "reflect",
        help="Regenerate the coach's private training thesis from recent context.",
    )
    reflect.add_argument(
        "--days",
        type=int,
        default=42,
        help="How many days of Strava activities to consider.",
    )

    debug_context = subparsers.add_parser(
        "debug-context",
        help="Print the context a normal coach reply would send to the model.",
    )
    debug_context.add_argument("message", help="Sample athlete message to debug.")
    debug_context.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Training lookback window in days.",
    )

    preview = subparsers.add_parser(
        "preview",
        help="Preview a scheduled message without sending it or mutating scheduler state.",
    )
    preview.add_argument("kind", choices=["morning", "evening", "weekly"])
    preview.add_argument(
        "--date",
        type=_parse_date,
        help="Coach-local date to preview, in YYYY-MM-DD format. Defaults to today.",
    )

    evals = subparsers.add_parser(
        "evals",
        help="Run local AI behavior evals.",
    )
    evals.add_argument(
        "--case",
        default=None,
        help="Eval case name or JSON path. Defaults to all cases.",
    )
    evals.add_argument(
        "--debug",
        action="store_true",
        help="Include saved plans, tool calls, and model replies in eval output.",
    )

    install_service = subparsers.add_parser(
        "install-telegram-service",
        help="Install and start the Telegram coach as a user systemd service.",
    )
    install_service.add_argument(
        "--no-enable",
        action="store_true",
        help="Write the service file without enabling it at boot.",
    )
    install_service.add_argument(
        "--no-start",
        action="store_true",
        help="Write and enable the service without starting it now.",
    )

    exchange = subparsers.add_parser("exchange-code", help="Exchange an OAuth code for tokens.")
    exchange.add_argument("code", help="Code copied from the Strava OAuth redirect URL.")

    telegram = subparsers.add_parser(
        "telegram",
        help="Run the Telegram running coach and monitor Strava for new runs.",
    )
    telegram.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Training lookback window in days.",
    )
    telegram.add_argument(
        "--poll-seconds",
        type=int,
        default=300,
        help="How often to check Strava for newly synced runs.",
    )
    telegram.add_argument(
        "--debug-log",
        action="store_true",
        help="Print internal debug log events to stdout.",
    )
    telegram.add_argument(
        "--trace-log",
        action="store_true",
        help="Print one-line interaction trace start/end events to stdout.",
    )

    repl = subparsers.add_parser(
        "repl",
        help="Chat with the running coach locally.",
    )
    repl.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Training lookback window in days.",
    )
    repl.add_argument(
        "--debug-log",
        action="store_true",
        help="Print internal debug log events and rx/tx log lines.",
    )
    repl.add_argument(
        "--trace-log",
        action="store_true",
        help="Print one-line interaction trace start/end events to stdout.",
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

    if args.command == "sync-strava":
        result = sync_strava_runs(StravaClient(), days=args.days)
        print(
            "Synced "
            f"{result['runs_seen']} Strava runs; "
            f"saved {result['summaries_saved']} summaries; "
            f"fetched {result['details_fetched']} detailed activities."
        )
        return 0

    if args.command == "strava-store-health":
        print(format_local_store_health(local_store_health()))
        return 0

    if args.command == "run-memory":
        if args.sync:
            result = sync_strava_runs(StravaClient(), days=args.days)
            print(
                "Synced "
                f"{result['runs_seen']} Strava runs; "
                f"saved {result['summaries_saved']} summaries; "
                f"fetched {result['details_fetched']} detailed activities."
            )
        data = refresh_run_memory(days=args.days)
        runs = data.get("runs") if isinstance(data.get("runs"), list) else []
        print(f"Refreshed run memory with {len(runs)} runs over {args.days} days.")
        print(run_memory_context(runs))
        if args.validate:
            validation = validate_run_memory(records=runs)
            print(_format_run_memory_validation(validation))
            if not validation["ok"]:
                return 1
        return 0

    if args.command == "reflect":
        reflection = generate_coach_reflection(StravaClient(), lookback_days=args.days)
        print(reflection)
        return 0

    if args.command == "debug-context":
        coach = CoachAgent(lookback_days=args.days, strava_client=StravaClient())
        print(coach.debug_context(args.message))
        return 0

    if args.command == "preview":
        preview = preview_scheduled_message(
            args.kind,
            client=StravaClient(),
            target_date=args.date,
            state=load_agent_state(STATE_PATH),
        )
        print(format_scheduled_preview(preview))
        return 0

    if args.command == "evals":
        argv = []
        if args.case:
            argv.extend(["--case", args.case])
        if args.debug:
            argv.append("--debug")
        return eval_runner_main(argv)

    if args.command == "install-telegram-service":
        service_path = install_telegram_user_service(
            enable=not args.no_enable,
            start=not args.no_start,
        )
        print(f"Installed Telegram service: {service_path}")
        if not args.no_enable:
            print("Enabled user service: running-agent-telegram.service")
        if not args.no_start:
            print("Started user service: running-agent-telegram.service")
        print(boot_linger_hint())
        return 0

    if args.command == "telegram":
        if args.debug_log:
            os.environ["RUNNING_AGENT_DEBUG_LOG"] = "1"
        if args.trace_log:
            os.environ["RUNNING_AGENT_TRACE_LOG"] = "1"
        transport = TelegramTransport(poll_seconds=args.poll_seconds, lookback_days=args.days)
        transport.run_forever()
        return 0

    if args.command == "repl":
        if args.trace_log:
            os.environ["RUNNING_AGENT_TRACE_LOG"] = "1"
        if not args.debug_log and not args.trace_log:
            os.environ["RUNNING_AGENT_QUIET_LOG"] = "1"
        state = load_agent_state(STATE_PATH)
        coach = CoachAgent(
            lookback_days=args.days,
            state=state,
            save_state=lambda: save_agent_state(state, STATE_PATH),
        )
        ReplTransport(coach).run()
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be in YYYY-MM-DD format") from error


def _format_run_memory_validation(validation: dict[str, object]) -> str:
    status = "OK" if validation.get("ok") else "FAILED"
    lines = [
        f"Run memory validation: {status}",
        f"Feedback entries: {validation.get('feedback_entries', 0)}",
        f"Run records: {validation.get('run_records', 0)}",
    ]
    missing = validation.get("missing_feedback")
    if isinstance(missing, list) and missing:
        lines.append(f"Missing feedback mappings: {len(missing)}")
        for entry in missing[:5]:
            lines.append(f"- {_format_feedback_identity(entry)}")
    stale = validation.get("stale_feedback")
    if isinstance(stale, list) and stale:
        lines.append(f"Stale feedback mappings: {len(stale)}")
        for entry in stale[:5]:
            lines.append(f"- {_format_feedback_identity(entry)}")
    return "\n".join(lines)


def _format_feedback_identity(entry: object) -> str:
    if not isinstance(entry, dict):
        return str(entry)
    parts = []
    for key in ("run_date", "activity_id", "raw"):
        if entry.get(key) is not None:
            parts.append(f"{key}={entry[key]}")
    return ", ".join(parts) if parts else str(entry)
