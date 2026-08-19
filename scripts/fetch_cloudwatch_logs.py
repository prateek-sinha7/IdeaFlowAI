#!/usr/bin/env python3
"""
fetch_cloudwatch_logs.py

Fetch CloudWatch Logs for a given log group and time window, and write them
to a plain text file formatted like a terminal log tail (one entry per line,
chronological, human-readable) -- no emoji/encoding crashes since this uses
boto3 directly instead of shelling out to the AWS CLI.

Usage examples:
    # Last 20 minutes, default log group and output file
    python scripts/fetch_cloudwatch_logs.py

    # Custom window and output file
    python scripts/fetch_cloudwatch_logs.py --minutes 60 --output logs/dev-app-1h.txt

    # Custom log group / profile / region
    python scripts/fetch_cloudwatch_logs.py \
        --log-group /velocityai/dev/app \
        --profile uki-velocity \
        --region eu-central-1 \
        --minutes 20 \
        --output dev-app-logs-last-20min.txt

    # Filter by keyword (CloudWatch Logs Insights filter on @message)
    python scripts/fetch_cloudwatch_logs.py --filter "AccessDeniedException"

    # Absolute time range instead of a rolling window
    python scripts/fetch_cloudwatch_logs.py \
        --start "2026-08-13T08:00:00" --end "2026-08-13T09:00:00"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_LOG_GROUP = "/velocityai/dev/app"
DEFAULT_REGION = "eu-central-1"
DEFAULT_MINUTES = 20
DEFAULT_OUTPUT = "dev-app-logs.txt"
POLL_INTERVAL_SECONDS = 1.5
POLL_TIMEOUT_SECONDS = 120


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch CloudWatch Logs into a clean, terminal-style text file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--log-group",
        default=DEFAULT_LOG_GROUP,
        help="CloudWatch Logs group name to query.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="AWS named profile to use (e.g. uki-velocity). Omit to use the default credential chain.",
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help="AWS region the log group lives in.",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_MINUTES,
        help="Rolling window: fetch logs from the last N minutes (ignored if --start is given).",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Absolute start time, e.g. '2026-08-13T08:00:00' (UTC, ISO 8601). Overrides --minutes.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Absolute end time, e.g. '2026-08-13T09:00:00' (UTC, ISO 8601). Defaults to now.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        help="Path to the output .txt file.",
    )
    parser.add_argument(
        "--filter",
        default=None,
        help="Optional substring/keyword to filter @message on (CloudWatch Logs Insights 'like' filter).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum number of log records to fetch.",
    )
    parser.add_argument(
        "--descending",
        action="store_true",
        help="Sort newest-first instead of the default oldest-first (chronological) order.",
    )
    return parser.parse_args()


def resolve_time_range(args: argparse.Namespace) -> tuple[int, int]:
    """Return (start_epoch_seconds, end_epoch_seconds)."""
    if args.end:
        end_dt = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    else:
        end_dt = datetime.now(timezone.utc)

    if args.start:
        start_dt = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    else:
        start_dt = end_dt - timedelta(minutes=args.minutes)

    if start_dt >= end_dt:
        raise ValueError("start time must be before end time")

    return int(start_dt.timestamp()), int(end_dt.timestamp())


def build_query_string(filter_text: str | None, descending: bool) -> str:
    order = "desc" if descending else "asc"
    base = "fields @timestamp, @message"
    if filter_text:
        # Escape double quotes defensively; Insights 'like' does a substring match.
        safe_filter = filter_text.replace('"', '\\"')
        base += f' | filter @message like "{safe_filter}"'
    base += f" | sort @timestamp {order}"
    return base


def run_insights_query(
    logs_client: Any,
    log_group: str,
    start_epoch: int,
    end_epoch: int,
    query_string: str,
    limit: int,
) -> list[dict[str, str]]:
    """Start a CloudWatch Logs Insights query, poll until done, return raw results."""
    start_response = logs_client.start_query(
        logGroupName=log_group,
        startTime=start_epoch,
        endTime=end_epoch,
        queryString=f"{query_string} | limit {limit}",
    )
    query_id = start_response["queryId"]

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        result = logs_client.get_query_results(queryId=query_id)
        status = result["status"]
        if status in ("Complete", "Failed", "Cancelled", "Timeout"):
            if status != "Complete":
                raise RuntimeError(f"CloudWatch Logs Insights query ended with status={status}")
            return result["results"]
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"CloudWatch Logs Insights query did not finish within {POLL_TIMEOUT_SECONDS}s"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def format_record(record: list[dict[str, str]]) -> str:
    """Turn one Insights result row into a single terminal-style log line."""
    fields = {item["field"]: item["value"] for item in record}
    timestamp = fields.get("@timestamp", "")
    message_raw = fields.get("@message", "")

    try:
        parsed = json.loads(message_raw)
    except (json.JSONDecodeError, TypeError):
        return f"{timestamp} {message_raw}"

    if isinstance(parsed, dict) and "level" in parsed and "logger" in parsed:
        level = parsed.get("level", "")
        logger = parsed.get("logger", "")
        inner_message = parsed.get("message", "")
        return f"{timestamp} [{level}] {logger}: {inner_message}"

    return f"{timestamp} {message_raw}"


def main() -> int:
    args = parse_args()

    try:
        start_epoch, end_epoch = resolve_time_range(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    session_kwargs: dict[str, str] = {}
    if args.profile:
        session_kwargs["profile_name"] = args.profile
    session = boto3.Session(**session_kwargs)

    logs_client = session.client(
        "logs",
        region_name=args.region,
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )

    query_string = build_query_string(args.filter, args.descending)

    start_label = datetime.fromtimestamp(start_epoch, tz=timezone.utc).isoformat()
    end_label = datetime.fromtimestamp(end_epoch, tz=timezone.utc).isoformat()
    print(f"Querying log group '{args.log_group}' in {args.region} "
          f"from {start_label} to {end_label}...")

    try:
        raw_results = run_insights_query(
            logs_client, args.log_group, start_epoch, end_epoch, query_string, args.limit
        )
    except (ClientError, BotoCoreError) as exc:
        print(f"error: AWS request failed: {exc}", file=sys.stderr)
        return 1
    except (RuntimeError, TimeoutError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    lines = [format_record(record) for record in raw_results]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    print(f"Saved {len(lines)} log lines to {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
