from __future__ import annotations

import argparse
import os
import time
import traceback
from datetime import date, datetime
from pathlib import Path

from .activity_format import activity_headline, detailed_activity_context
from .auth import build_authorization_url
from .feedback import summarize_training
from .garmin_context import garmin_readiness_context, garmin_weekly_context
from .goal_store import save_training_goal, training_goal_context
from .plan_store import save_weekly_plan, weekly_plan_context
from .plan_suggestion import next_week_start, suggest_next_week_plan
from .run_summary import run_summary_for_date
from .strava_client import StravaClient
from .telegram_agent import TelegramRunningAgent
from .weekly_review import current_week_start, review_week


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

    subparsers.add_parser(
        "garmin-context",
        help="Print a compact Garmin readiness context for coaching.",
    )

    garmin_weekly = subparsers.add_parser(
        "garmin-weekly-context",
        help="Print a compact Garmin recovery trend context for planning.",
    )
    garmin_weekly.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of Garmin days to summarize.",
    )

    exchange = subparsers.add_parser("exchange-code", help="Exchange an OAuth code for tokens.")
    exchange.add_argument("code", help="Code copied from the Strava OAuth redirect URL.")

    recent = subparsers.add_parser("recent", help="Fetch recent Strava runs and summarize them.")
    recent.add_argument("--days", type=int, default=14, help="Lookback window in days.")

    latest = subparsers.add_parser("latest-run", help="Print the latest Strava run.")
    latest.add_argument("--days", type=int, default=90, help="Lookback window in days.")

    latest_detail = subparsers.add_parser(
        "latest-run-detail",
        help="Print lap-by-lap detail for the latest Strava run.",
    )
    latest_detail.add_argument("--days", type=int, default=90, help="Lookback window in days.")

    run_detail = subparsers.add_parser(
        "run-detail",
        help="Print lap-by-lap detail for runs on a specific local date.",
    )
    run_detail.add_argument("date", help="Local date to inspect, formatted YYYY-MM-DD.")
    run_detail.add_argument(
        "--search-days",
        type=int,
        default=120,
        help="How far back to search Strava activities.",
    )
    run_detail.add_argument(
        "--all",
        action="store_true",
        help="Print every run found on that date instead of only the latest one.",
    )

    run_summary = subparsers.add_parser(
        "run-summary",
        help="Generate a coaching summary for a run on a specific local date.",
    )
    run_summary.add_argument("date", help="Local date to summarize, formatted YYYY-MM-DD.")
    run_summary.add_argument(
        "--search-days",
        type=int,
        default=120,
        help="How far back to search Strava activities.",
    )

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

    last_run = subparsers.add_parser(
        "send-last-run",
        help="Send a Telegram workout summary for the latest Strava run.",
    )
    last_run.add_argument("--days", type=int, default=21, help="Training lookback window in days.")

    send_run_summary = subparsers.add_parser(
        "send-run-summary",
        help="Send a Telegram workout summary for a run on a specific local date.",
    )
    send_run_summary.add_argument("date", help="Local date to summarize, formatted YYYY-MM-DD.")
    send_run_summary.add_argument(
        "--search-days",
        type=int,
        default=120,
        help="How far back to search Strava activities.",
    )

    suggest_plan = subparsers.add_parser(
        "suggest-plan",
        help="Print a suggested training plan idea for next week.",
    )
    suggest_plan.add_argument(
        "--days",
        type=int,
        default=42,
        help="Training lookback window in days.",
    )
    suggest_plan.add_argument(
        "--week-start",
        help="Target Monday for the suggested plan, formatted YYYY-MM-DD.",
    )

    weekly_review = subparsers.add_parser(
        "weekly-review",
        help="Print and log a review of the current training week.",
    )
    weekly_review.add_argument(
        "--week-start",
        help="Target Monday for the week to review, formatted YYYY-MM-DD.",
    )
    weekly_review.add_argument(
        "--no-log",
        action="store_true",
        help="Do not append the review to the local coach log.",
    )

    set_plan = subparsers.add_parser(
        "set-plan", help="Save a weekly training plan from a text file."
    )
    set_plan.add_argument("path", help="Path to a plain-text weekly plan.")

    subparsers.add_parser("show-plan", help="Print the saved weekly training plan.")

    set_goal = subparsers.add_parser("set-goal", help="Save an overall training goal from text.")
    set_goal.add_argument("goal", help="Goal text, quoted if it contains spaces.")

    subparsers.add_parser("show-goal", help="Print the saved overall training goal.")

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

    if args.command == "garmin-context":
        print(garmin_readiness_context())
        return 0

    if args.command == "garmin-weekly-context":
        print(garmin_weekly_context(days=args.days))
        return 0

    if args.command == "recent":
        client = StravaClient()
        activities = client.recent_activities(days=args.days)
        print(summarize_training(activities, days=args.days))
        return 0

    if args.command == "latest-run":
        client = StravaClient()
        activity = client.latest_run(days=args.days)
        if not activity:
            print(f"No Strava runs found in the last {args.days} days.")
            return 1
        print(activity_headline(activity))
        return 0

    if args.command == "latest-run-detail":
        client = StravaClient()
        activity = client.latest_run(days=args.days)
        if not activity:
            print(f"No Strava runs found in the last {args.days} days.")
            return 1
        detailed = client.detailed_activity(activity["id"])
        print(detailed_activity_context(detailed, target_date=_activity_date(detailed)))
        return 0

    if args.command == "run-detail":
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        client = StravaClient()
        activities = client.runs_on_date(target_date, search_days=args.search_days)
        if not activities:
            print(f"No Strava runs found on {target_date.isoformat()}.")
            return 1
        selected = activities if args.all else activities[:1]
        for index, activity in enumerate(selected):
            if index:
                print("\n---\n")
            detailed = client.detailed_activity(activity["id"])
            print(detailed_activity_context(detailed, target_date=target_date))
        if len(activities) > 1 and not args.all:
            print(
                f"\n{len(activities) - 1} additional run(s) found on this date. Use --all to print them."
            )
        return 0

    if args.command == "run-summary":
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        client = StravaClient()
        print(run_summary_for_date(client, target_date, search_days=args.search_days))
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

    if args.command == "send-last-run":
        agent = TelegramRunningAgent(lookback_days=args.days)
        agent.send_last_run_summary()
        print("Sent latest-run summary to Telegram.")
        return 0

    if args.command == "send-run-summary":
        agent = TelegramRunningAgent()
        agent.send_run_summary_for_date(args.date, search_days=args.search_days)
        print("Sent run summary to Telegram.")
        return 0

    if args.command == "suggest-plan":
        target_week_start = (
            datetime.strptime(args.week_start, "%Y-%m-%d").date()
            if args.week_start
            else next_week_start(datetime.now().astimezone().date())
        )
        client = StravaClient()
        print(
            suggest_next_week_plan(
                client,
                target_week_start=target_week_start,
                lookback_days=args.days,
            )
        )
        return 0

    if args.command == "weekly-review":
        week_start = (
            datetime.strptime(args.week_start, "%Y-%m-%d").date()
            if args.week_start
            else current_week_start(datetime.now().astimezone().date())
        )
        client = StravaClient()
        print(review_week(client, week_start=week_start, log_review=not args.no_log))
        return 0

    if args.command == "set-plan":
        plan_text = Path(args.path).read_text(encoding="utf-8")
        save_weekly_plan(plan_text)
        print("Saved weekly training plan.")
        return 0

    if args.command == "show-plan":
        print(weekly_plan_context())
        return 0

    if args.command == "set-goal":
        save_training_goal(args.goal)
        print("Saved overall training goal.")
        return 0

    if args.command == "show-goal":
        print(training_goal_context())
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_telegram_with_restarts(
    poll_seconds: int,
    lookback_days: int,
    restart_delay: int,
) -> None:
    print("Running Telegram coach with restart-on-crash enabled. " "Press Ctrl+C to stop.")
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


def _activity_date(activity: dict) -> date:
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return datetime.now().astimezone().date()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return datetime.now().astimezone().date()
