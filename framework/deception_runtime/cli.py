"""
CLI commands for deception runtime.

Usage:
    python -m deception_runtime.cli validate --instances-dir deceptions/instances/generated
    python -m deception_runtime.cli list --instances-dir deceptions/instances/generated --limit 10
"""

import argparse
import json
import sys
from pathlib import Path

from deception_runtime.logging import StructuredLogger
from deception_runtime.registry import DeceptionRegistry

logger = StructuredLogger(__name__)


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Validate the deception registry.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    instances_dir = Path(args.instances_dir)
    schema_path = Path(args.schema_path) if args.schema_path else None

    print(f"Validating deception registry: {instances_dir}")
    print()

    try:
        registry = DeceptionRegistry(
            instances_dir=instances_dir,
            schema_path=schema_path,
            validate_schema=args.validate_schema,
        )

        print(f"✓ Registry loaded successfully")
        print(f"  Total instances: {len(registry)}")
        print()

        # Print statistics
        stats = registry.stats()

        print("Statistics:")
        print(f"  Total instances: {stats['total_instances']}")
        print(f"  Total routes: {stats['total_routes']}")
        print()

        print("By channel:")
        for channel, count in sorted(stats['by_channel'].items()):
            print(f"  {channel}: {count}")
        print()

        print("By surface:")
        for surface, count in sorted(stats['by_surface'].items()):
            print(f"  {surface}: {count}")
        print()

        if stats['by_primitive']:
            print(f"Unique primitives: {len(stats['by_primitive'])}")
            print()

        if args.json:
            print("JSON output:")
            print(json.dumps(stats, indent=2))

        return 0

    except Exception as e:
        print(f"✗ Validation failed: {e}", file=sys.stderr)
        logger.exception("Registry validation failed")
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """
    List instances in the registry.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    instances_dir = Path(args.instances_dir)

    try:
        registry = DeceptionRegistry(
            instances_dir=instances_dir,
            schema_path=None,
            validate_schema=False,
        )

        instance_ids = registry.list_ids(limit=args.limit)

        print(f"Instances in {instances_dir}:")
        print(f"  Showing {len(instance_ids)} of {len(registry)} total")
        print()

        for instance_id in instance_ids:
            instance = registry.get(instance_id)
            if instance:
                route_str = f" → {instance.route}" if instance.route else ""
                print(f"  {instance_id}")
                print(f"    Channel: {instance.channel}.{instance.surface}{route_str}")
                if instance.primitive_id:
                    print(f"    Primitive: {instance.primitive_id}")

        return 0

    except Exception as e:
        print(f"✗ Failed to list instances: {e}", file=sys.stderr)
        logger.exception("List command failed")
        return 1


def main() -> int:
    """
    Main CLI entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Deception Runtime CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate the deception registry",
    )
    validate_parser.add_argument(
        "--instances-dir",
        default="deceptions/instances/generated",
        help="Directory containing resolved instance files (default: deceptions/instances/generated)",
    )
    validate_parser.add_argument(
        "--schema-path",
        default="deceptions/schemas/deception.schema.json",
        help="Path to JSON schema (default: deceptions/schemas/deception.schema.json)",
    )
    validate_parser.add_argument(
        "--no-validate-schema",
        dest="validate_schema",
        action="store_false",
        default=True,
        help="Skip JSON schema validation",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output statistics as JSON",
    )

    # List command
    list_parser = subparsers.add_parser(
        "list",
        help="List instances in the registry",
    )
    list_parser.add_argument(
        "--instances-dir",
        default="deceptions/instances/generated",
        help="Directory containing resolved instance files (default: deceptions/instances/generated)",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of instances to show",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "validate":
        return cmd_validate(args)
    elif args.command == "list":
        return cmd_list(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
