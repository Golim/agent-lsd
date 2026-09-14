"""
CLI commands for telemetry inspection.

Usage:
    python -m deception_runtime.cli_telemetry validate-events --path verification/telemetry.jsonl
    python -m deception_runtime.cli_telemetry stats --path verification/telemetry.jsonl
    python -m deception_runtime.cli_telemetry query --path verification/telemetry.jsonl --event-type honeytoken_hit
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

from deception_runtime.events import validate_event
from deception_runtime.logging import StructuredLogger

logger = StructuredLogger(__name__)


def cmd_validate_events(args: argparse.Namespace) -> int:
    """
    Validate telemetry events in a JSONL file.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    path = Path(args.path)

    if not path.exists():
        print(f"✗ File not found: {path}", file=sys.stderr)
        return 1

    print(f"Validating telemetry events: {path}")
    print()

    valid_count = 0
    invalid_count = 0
    line_num = 0

    try:
        with open(path) as f:
            for line in f:
                line_num += 1

                try:
                    event = json.loads(line)

                    if validate_event(event, strict=args.strict):
                        valid_count += 1
                    else:
                        invalid_count += 1
                        if args.verbose:
                            print(f"Line {line_num}: Invalid event")

                except json.JSONDecodeError as e:
                    invalid_count += 1
                    if args.verbose:
                        print(f"Line {line_num}: JSON parse error: {e}")

        print(f"✓ Validation complete")
        print(f"  Total events: {line_num}")
        print(f"  Valid: {valid_count}")
        print(f"  Invalid: {invalid_count}")
        print()

        return 0 if invalid_count == 0 else 1

    except Exception as e:
        print(f"✗ Validation failed: {e}", file=sys.stderr)
        return 1


def cmd_stats(args: argparse.Namespace) -> int:
    """
    Compute statistics from telemetry events.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    path = Path(args.path)

    if not path.exists():
        print(f"✗ File not found: {path}", file=sys.stderr)
        return 1

    print(f"Computing telemetry statistics: {path}")
    print()

    try:
        event_types = Counter()
        challenges = Counter()
        instances = Counter()
        students = Counter()
        routes = Counter()
        status_codes = Counter()
        honeytokens_by_type = Counter()

        events_data = []

        # Read JSONL or SQLite
        if str(path).endswith(".jsonl"):
            with open(path) as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        events_data.append(event)
                    except json.JSONDecodeError:
                        pass
        elif str(path).endswith(".sqlite"):
            conn = sqlite3.connect(str(path))
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events")

            columns = [desc[0] for desc in cursor.description]
            for row in cursor:
                event = dict(zip(columns, row))
                # Parse extra_json
                if event.get("extra_json"):
                    try:
                        event["extra"] = json.loads(event["extra_json"])
                    except:
                        event["extra"] = {}
                events_data.append(event)

            conn.close()

        # Compute statistics
        for event in events_data:
            event_types[event.get("event_type")] += 1
            challenges[event.get("challenge_id")] += 1

            if event.get("instance_id"):
                instances[event.get("instance_id")] += 1

            if event.get("student_id"):
                students[event.get("student_id")] += 1

            routes[event.get("route")] += 1

            if event.get("status_code"):
                status_codes[event.get("status_code")] += 1

            # Honeytoken statistics
            if event.get("event_type") == "honeytoken_hit":
                extra = event.get("extra", {})
                token_type = extra.get("token_type", "unknown")
                honeytokens_by_type[token_type] += 1

        # Print statistics
        print(f"Total events: {len(events_data)}")
        print()

        print("Event types:")
        for event_type, count in event_types.most_common():
            print(f"  {event_type}: {count}")
        print()

        print(f"Unique challenges: {len(challenges)}")
        print(f"Unique instances: {len(instances)}")
        print(f"Unique students: {len(students)}")
        print(f"Unique routes: {len(routes)}")
        print()

        if status_codes:
            print("Status codes:")
            for code, count in sorted(status_codes.items()):
                print(f"  {code}: {count}")
            print()

        if honeytokens_by_type:
            print("Honeytoken hits by type:")
            for token_type, count in honeytokens_by_type.most_common():
                print(f"  {token_type}: {count}")
            print()

        if args.top:
            print(f"Top {args.top} instances:")
            for instance_id, count in instances.most_common(args.top):
                print(f"  {instance_id}: {count}")
            print()

            if students:
                print(f"Top {args.top} students:")
                for student_id, count in students.most_common(args.top):
                    print(f"  {student_id}: {count}")
                print()

        if args.json:
            stats_json = {
                "total_events": len(events_data),
                "event_types": dict(event_types),
                "unique_challenges": len(challenges),
                "unique_instances": len(instances),
                "unique_students": len(students),
                "unique_routes": len(routes),
                "status_codes": dict(status_codes),
                "honeytoken_hits_by_type": dict(honeytokens_by_type),
            }
            print("JSON output:")
            print(json.dumps(stats_json, indent=2))

        return 0

    except Exception as e:
        print(f"✗ Failed to compute statistics: {e}", file=sys.stderr)
        logger.exception("Stats command failed")
        return 1


def cmd_query(args: argparse.Namespace) -> int:
    """
    Query telemetry events.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    path = Path(args.path)

    if not path.exists():
        print(f"✗ File not found: {path}", file=sys.stderr)
        return 1

    try:
        matches = []

        # Read events
        if str(path).endswith(".jsonl"):
            with open(path) as f:
                for line in f:
                    try:
                        event = json.loads(line)

                        # Apply filters
                        if args.event_type and event.get("event_type") != args.event_type:
                            continue
                        if args.instance_id and event.get("instance_id") != args.instance_id:
                            continue
                        if args.student_id and event.get("student_id") != args.student_id:
                            continue
                        if args.route and event.get("route") != args.route:
                            continue

                        matches.append(event)

                    except json.JSONDecodeError:
                        pass

        # Print matches
        print(f"Found {len(matches)} matching events")
        print()

        for event in matches[:args.limit]:
            print(json.dumps(event, indent=2))
            print()

        if len(matches) > args.limit:
            print(f"... and {len(matches) - args.limit} more")

        return 0

    except Exception as e:
        print(f"✗ Query failed: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """
    Main CLI entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Telemetry CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Validate events command
    validate_parser = subparsers.add_parser(
        "validate-events",
        help="Validate telemetry events",
    )
    validate_parser.add_argument(
        "--path",
        required=True,
        help="Path to JSONL file",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict JSON schema validation",
    )
    validate_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show details for invalid events",
    )

    # Stats command
    stats_parser = subparsers.add_parser(
        "stats",
        help="Compute telemetry statistics",
    )
    stats_parser.add_argument(
        "--path",
        required=True,
        help="Path to JSONL or SQLite file",
    )
    stats_parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Show top N items (default: 10)",
    )
    stats_parser.add_argument(
        "--json",
        action="store_true",
        help="Output statistics as JSON",
    )

    # Query command
    query_parser = subparsers.add_parser(
        "query",
        help="Query telemetry events",
    )
    query_parser.add_argument(
        "--path",
        required=True,
        help="Path to JSONL or SQLite file",
    )
    query_parser.add_argument(
        "--event-type",
        help="Filter by event type",
    )
    query_parser.add_argument(
        "--instance-id",
        help="Filter by instance ID",
    )
    query_parser.add_argument(
        "--student-id",
        help="Filter by student ID",
    )
    query_parser.add_argument(
        "--route",
        help="Filter by route",
    )
    query_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit number of results (default: 10)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "validate-events":
        return cmd_validate_events(args)
    elif args.command == "stats":
        return cmd_stats(args)
    elif args.command == "query":
        return cmd_query(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
