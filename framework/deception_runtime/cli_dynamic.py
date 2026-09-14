"""
CLI commands for dynamic deception planning (rabbit holes and fake goals).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from deception_runtime.fake_goals import FakeGoalManager
from deception_runtime.logging import StructuredLogger
from deception_runtime.rabbit_holes import RabbitHoleManager
from deception_runtime.registry import DeceptionRegistry

logger = StructuredLogger(__name__)


def _build_managers(args: argparse.Namespace) -> tuple[RabbitHoleManager, FakeGoalManager]:
    rabbit = RabbitHoleManager(
        route_prefix=args.route_prefix,
        max_depth=args.rabbit_max_depth,
        max_branching=args.rabbit_max_branching,
        default_depth=min(3, args.rabbit_max_depth),
        default_branching=min(1, args.rabbit_max_branching),
    )
    fake = FakeGoalManager(
        route_prefix=args.route_prefix,
        default_mode=args.fake_goal_mode,
    )
    return rabbit, fake


def _load_registry(instances_dir: str) -> DeceptionRegistry:
    return DeceptionRegistry(
        instances_dir=Path(instances_dir),
        schema_path=None,
        validate_schema=False,
    )


def _instance_payload(
    instance,
    rabbit_manager: RabbitHoleManager,
    fake_goal_manager: FakeGoalManager,
    challenge_id: str,
    synthesize: bool,
) -> dict[str, Any]:
    rabbit_plan = rabbit_manager.build_plan(
        instance=instance,
        challenge_id=challenge_id,
        synthesize_when_missing=synthesize,
    )
    fake_plan = fake_goal_manager.build_plan(
        instance=instance,
        challenge_id=challenge_id,
        synthesize_when_missing=synthesize,
    )
    return {
        "instance_id": instance.instance_id,
        "rabbit_hole_supported": rabbit_plan is not None,
        "fake_goal_supported": fake_plan is not None,
        "rabbit_hole": rabbit_plan.to_dict() if rabbit_plan else None,
        "fake_goal": fake_plan.to_dict() if fake_plan else None,
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    """Inspect generated dynamic plans for one instance."""
    try:
        registry = _load_registry(args.instances_dir)
    except Exception as exc:
        print(f"✗ Failed to load registry: {exc}", file=sys.stderr)
        return 1

    instance = registry.get(args.instance_id)
    if not instance:
        print(f"✗ Instance not found: {args.instance_id}", file=sys.stderr)
        return 1

    rabbit_manager, fake_goal_manager = _build_managers(args)
    payload = _instance_payload(
        instance=instance,
        rabbit_manager=rabbit_manager,
        fake_goal_manager=fake_goal_manager,
        challenge_id=args.challenge_id,
        synthesize=not args.no_synthesize,
    )

    rabbit_plan = payload["rabbit_hole"]
    fake_plan = payload["fake_goal"]
    routes: list[str] = []
    if rabbit_plan:
        routes.extend(rabbit_plan.get("routes", []))
        terminal = rabbit_plan.get("terminal_path")
    else:
        terminal = None
    if fake_plan:
        routes.append(fake_plan["endpoint_path"])
        if rabbit_plan and rabbit_plan.get("terminal_mode") == "fake_goal":
            terminal = fake_plan["endpoint_path"]

    print(f"Instance: {args.instance_id}")
    print(f"Rabbit hole supported: {payload['rabbit_hole_supported']}")
    print(f"Fake goal supported: {payload['fake_goal_supported']}")
    if rabbit_plan:
        print(f"Rabbit depth: {rabbit_plan['depth']}")
    if terminal:
        print(f"Terminal endpoint: {terminal}")
    print("Generated routes:")
    for route in sorted(set(routes)):
        print(f"  {route}")

    if args.json:
        print()
        print(json.dumps(payload, indent=2, sort_keys=True))

    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Generate deterministic plan file for all instances."""
    try:
        registry = _load_registry(args.instances_dir)
    except Exception as exc:
        print(f"✗ Failed to load registry: {exc}", file=sys.stderr)
        return 1

    rabbit_manager, fake_goal_manager = _build_managers(args)
    instances: dict[str, Any] = {}

    for instance_id in sorted(registry.list_ids()):
        instance = registry.get(instance_id)
        if not instance:
            continue
        instances[instance_id] = _instance_payload(
            instance=instance,
            rabbit_manager=rabbit_manager,
            fake_goal_manager=fake_goal_manager,
            challenge_id=args.challenge_id,
            synthesize=True,
        )

    output = {
        "meta": {
            "route_prefix": args.route_prefix,
            "challenge_id": args.challenge_id,
            "rabbit_max_depth": args.rabbit_max_depth,
            "rabbit_max_branching": args.rabbit_max_branching,
            "fake_goal_mode": args.fake_goal_mode,
        },
        "instances": instances,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"✓ Wrote deterministic plan file: {out_path}")
    print(f"  Instances: {len(instances)}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate determinism and uniqueness of generated dynamic plans."""
    try:
        registry = _load_registry(args.instances_dir)
    except Exception as exc:
        print(f"✗ Failed to load registry: {exc}", file=sys.stderr)
        return 1

    rabbit_manager, fake_goal_manager = _build_managers(args)

    errors: list[str] = []
    seen_routes: dict[str, str] = {}
    shared_routes: set[str] = set()
    rabbit_count = 0
    fake_count = 0

    for instance_id in sorted(registry.list_ids()):
        instance = registry.get(instance_id)
        if not instance:
            continue

        rabbit_plan_1 = rabbit_manager.build_plan(instance, args.challenge_id, synthesize_when_missing=True)
        rabbit_plan_2 = rabbit_manager.build_plan(instance, args.challenge_id, synthesize_when_missing=True)
        fake_plan_1 = fake_goal_manager.build_plan(instance, args.challenge_id, synthesize_when_missing=True)
        fake_plan_2 = fake_goal_manager.build_plan(instance, args.challenge_id, synthesize_when_missing=True)

        if rabbit_plan_1:
            rabbit_count += 1
            if rabbit_plan_1.depth > args.rabbit_max_depth:
                errors.append(
                    f"{instance_id}: rabbit depth {rabbit_plan_1.depth} exceeds max {args.rabbit_max_depth}"
                )
            if rabbit_plan_2 and rabbit_plan_1.to_dict() != rabbit_plan_2.to_dict():
                errors.append(f"{instance_id}: rabbit plan is not deterministic")
            for path in rabbit_plan_1.route_paths():
                existing_owner = seen_routes.get(path)
                if existing_owner and existing_owner != instance_id:
                    shared_routes.add(path)
                else:
                    seen_routes[path] = instance_id

        if fake_plan_1:
            fake_count += 1
            if not fake_plan_2 or fake_plan_1.to_dict() != fake_plan_2.to_dict():
                errors.append(f"{instance_id}: fake-goal plan is not deterministic")
            existing_owner = seen_routes.get(fake_plan_1.endpoint_path)
            if existing_owner and existing_owner != instance_id:
                shared_routes.add(fake_plan_1.endpoint_path)
            else:
                seen_routes[fake_plan_1.endpoint_path] = instance_id

    if errors:
        print("✗ Dynamic plan validation failed")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("✓ Dynamic plan validation passed")
    print(f"  Rabbit-hole plans: {rabbit_count}")
    print(f"  Fake-goal plans: {fake_count}")
    print(f"  Unique routes: {len(seen_routes)}")
    print(f"  Shared canonical routes: {len(shared_routes)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dynamic deception planning CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    def add_common_flags(cmd):
        cmd.add_argument(
            "--instances-dir",
            default="deceptions/instances/generated",
            help="Directory containing resolved instance files",
        )
        cmd.add_argument(
            "--challenge-id",
            default="dynamic_challenge",
            help="Challenge id used for deterministic plan synthesis",
        )
        cmd.add_argument(
            "--route-prefix",
            default="/_deception",
            help="Dynamic route prefix (default: /_deception)",
        )
        cmd.add_argument(
            "--rabbit-max-depth",
            type=int,
            default=3,
            help="Maximum rabbit-hole depth",
        )
        cmd.add_argument(
            "--rabbit-max-branching",
            type=int,
            default=1,
            help="Maximum rabbit-hole branching",
        )
        cmd.add_argument(
            "--fake-goal-mode",
            choices=["flag", "success_message", "both"],
            default="both",
            help="Default fake-goal mode",
        )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect dynamic plan for one instance")
    add_common_flags(inspect_parser)
    inspect_parser.add_argument("--instance-id", required=True, help="Instance identifier")
    inspect_parser.add_argument(
        "--no-synthesize",
        action="store_true",
        help="Only inspect explicit instance.raw.dynamic settings",
    )
    inspect_parser.add_argument("--json", action="store_true", help="Print JSON output")

    plan_parser = subparsers.add_parser("plan", help="Generate deterministic plan file")
    add_common_flags(plan_parser)
    plan_parser.add_argument(
        "--output",
        default="dynamic_plans.json",
        help="Output JSON path (default: dynamic_plans.json)",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate generated dynamic plans")
    add_common_flags(validate_parser)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    if args.command == "inspect":
        return cmd_inspect(args)
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "validate":
        return cmd_validate(args)

    logger.error("Unknown command", command=args.command)
    return 1


if __name__ == "__main__":
    sys.exit(main())
