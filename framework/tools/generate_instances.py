#!/usr/bin/env python3

"""Automatic instance generator for web-CTF deception research.

Generates validated, deterministic deception instances from YAML primitives.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import local modules
from constraints import ConstraintChecker, ConstraintViolation, validate_placement_constraints
from generators import get_generator
from manifest import create_manifest, extract_manifest_entry
from validate import load_json_schema, validate_instance
from deception_runtime.config import DeceptionConfig, normalize_dynamic_route_style
from deception_runtime.dynamic_routes import resolve_dynamic_routes_for_instance
from deception_runtime.registry import DeceptionInstance


def hash_seed(*components: str | int) -> int:
    """Create a deterministic seed from components.

    Args:
        components: Strings or integers to hash together

    Returns:
        Integer seed suitable for random.Random()
    """
    hasher = hashlib.sha256()
    for i, component in enumerate(components):
        # Add position index to increase entropy
        hasher.update(f"{i}:".encode("utf-8"))
        hasher.update(str(component).encode("utf-8"))
        hasher.update(b":")
    # Convert hash to int, use more bytes for better distribution
    return int.from_bytes(hasher.digest()[:8], byteorder="big")


def load_primitives(primitives_dir: Path) -> List[Dict[str, Any]]:
    """Load all primitive YAML files.

    Args:
        primitives_dir: Directory containing primitive files

    Returns:
        List of primitive dictionaries with metadata
    """
    primitives = []

    # Find all .primitive.yaml files recursively
    for yaml_file in primitives_dir.rglob("*.primitive.yaml"):
        with open(yaml_file, "r", encoding="utf-8") as f:
            primitive = yaml.safe_load(f)

        # Add metadata
        primitive["_source_file"] = str(yaml_file.relative_to(primitives_dir))

        # Ensure primitive_id exists
        if "primitive_id" not in primitive:
            # Derive from filename
            primitive["primitive_id"] = yaml_file.stem.replace(".primitive", "")

        primitives.append(primitive)

    return primitives


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Override dictionary (takes precedence)

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def render_template(template: str, variables: Dict[str, str]) -> str:
    """Render a template string with variables.

    Replaces {{var}} with values from variables dict.

    Args:
        template: Template string with {{var}} placeholders
        variables: Dictionary of variable values

    Returns:
        Rendered string
    """
    result = template
    for var, value in variables.items():
        placeholder = f"{{{{{var}}}}}"
        result = result.replace(placeholder, str(value))
    return result


def fill_missing_placement_fields(instance: Dict[str, Any], rng: random.Random) -> None:
    """Fill in missing required placement fields.

    Some primitives may have incomplete placement sections.
    This adds reasonable defaults based on the surface type.

    Args:
        instance: Instance dictionary
        rng: Random number generator for generating selectors
    """
    perception = instance.get("perception", {})
    surface = perception.get("surface", "")
    placement = instance.get("placement", {})

    # Map surface to required attribute
    surface_to_attribute = {
        "aria_label": "aria-label",
        "aria_description": "aria-description",
        "alt_text": "alt",
        "title_attr": "title",
    }

    # Add attribute if needed
    if surface in surface_to_attribute and "attribute" not in placement:
        placement["attribute"] = surface_to_attribute[surface]

    # Add selector if needed for DOM surfaces
    dom_surfaces = [
        "aria_label", "aria_description", "alt_text", "title_attr",
        "text_node", "hidden_div", "offscreen_div", "comment",
        "meta_tag", "js_generated_dom"
    ]

    if surface in dom_surfaces and "selector" not in placement:
        # Generate a reasonable selector
        selector_options = [
            "#main-content",
            "#header",
            "#footer",
            "#sidebar",
            ".container",
            ".content",
            "body",
            "main",
        ]
        placement["selector"] = rng.choice(selector_options)

    # Add canvas_id and coordinates if needed
    if surface == "canvas_drawtext":
        if "canvas_id" not in placement:
            placement["canvas_id"] = f"canvas-{rng.randint(1, 99)}"
        if "coordinates" not in placement:
            placement["coordinates"] = [
                rng.randint(10, 400),
                rng.randint(10, 300)
            ]

    instance["placement"] = placement

    # Fill in honeytoken fields if enabled but incomplete
    honeytoken = instance.get("honeytoken", {})
    if honeytoken.get("enabled", False):
        if "token_id_template" not in honeytoken:
            instance_id = instance.get("id", "unknown")
            honeytoken["token_id_template"] = f"{instance_id}-{{{{seed}}}}"
        if "sink" not in honeytoken:
            honeytoken["sink"] = "server_log"
        instance["honeytoken"] = honeytoken


def resolve_randomization(
    instance: Dict[str, Any],
    rng: random.Random
) -> Dict[str, str]:
    """Resolve randomization parameters for an instance.

    Args:
        instance: Instance dictionary with randomization config
        rng: Seeded random number generator

    Returns:
        Dictionary of variable_name -> generated_value
    """
    randomization = instance.get("randomization", {})
    if not randomization.get("enabled", True):
        return {}

    parameters = randomization.get("parameters", {})
    variables = {}

    for var_name, config in parameters.items():
        generator_name = config.get("generator")
        options = config.get("options", {})

        try:
            generator = get_generator(generator_name)
            variables[var_name] = generator(rng, options)
        except Exception as e:
            raise ValueError(
                f"Failed to generate '{var_name}' with generator '{generator_name}': {e}"
            )

    return variables


def build_dynamic_generation_config(
    *,
    challenge_id: str,
    route_style: str,
    route_prefix: str = "/_deception",
) -> DeceptionConfig:
    """Create the dynamic-route config used while rendering source primitives."""
    return DeceptionConfig.from_flask_config(
        {
            "DECEPTIONS_DYNAMIC_ENABLED": True,
            "DECEPTIONS_RABBIT_HOLES_ENABLED": True,
            "DECEPTIONS_FAKE_GOALS_ENABLED": True,
            "DECEPTIONS_DYNAMIC_ROUTE_PREFIX": route_prefix,
            "DECEPTIONS_DYNAMIC_ROUTE_STYLE": normalize_dynamic_route_style(route_style),
            "DECEPTIONS_RABBIT_MAX_DEPTH": 2,
            "DECEPTIONS_RABBIT_MAX_BRANCHING": 1,
            "DECEPTIONS_FAKE_GOAL_MODE": "both",
            "DECEPTIONS_CHALLENGE_ID": challenge_id,
        },
        app_name="generate_instances",
    )


def resolve_dynamic_template_variables(
    instance: Dict[str, Any],
    config: DeceptionConfig,
    variables: Dict[str, str],
) -> Dict[str, str]:
    """Resolve runtime dynamic routes for template rendering."""
    if not isinstance(instance.get("dynamic"), dict):
        return {}

    deception_instance = DeceptionInstance.from_dict(instance, "generated-memory")
    resolution = resolve_dynamic_routes_for_instance(
        instance=deception_instance,
        config=config,
        route_hint_path=variables.get("decoy_path"),
        synthesize_when_missing=True,
    )
    return resolution.template_variables()


def render_instance_templates(
    instance: Dict[str, Any],
    variables: Dict[str, str]
) -> None:
    """Render all templates in an instance (in-place).

    Args:
        instance: Instance dictionary
        variables: Variables for template rendering
    """
    # Render payload content_template
    payload = instance.get("payload", {})
    if "content_template" in payload:
        payload["content_template"] = render_template(
            payload["content_template"],
            variables
        )

    # Render honeytoken token_id_template
    honeytoken = instance.get("honeytoken", {})
    if "token_id_template" in honeytoken:
        honeytoken["token_id_template"] = render_template(
            honeytoken["token_id_template"],
            variables
        )

    # Render artifacts
    artifacts = payload.get("artifacts", [])
    for artifact in artifacts:
        if "name" in artifact:
            artifact["name"] = render_template(artifact["name"], variables)


def generate_instance_id(primitive_id: str, index: int) -> str:
    """Generate a unique instance ID.

    Args:
        primitive_id: Primitive identifier
        index: Instance index

    Returns:
        Instance ID string
    """
    return f"{primitive_id}_{index:03d}"


def generate_single_instance(
    primitive: Dict[str, Any],
    index: int,
    global_seed: int,
    schema: Dict[str, Any],
    constraint_checker: ConstraintChecker,
    dynamic_config: DeceptionConfig,
    max_retries: int = 10
) -> Tuple[Dict[str, Any], int]:
    """Generate a single instance from a primitive.

    Args:
        primitive: Primitive definition
        index: Instance index
        global_seed: Global seed
        schema: JSON Schema for validation
        constraint_checker: Constraint checker
        max_retries: Maximum generation retries

    Returns:
        Tuple of (instance_dict, seed_used)

    Raises:
        ValueError: If generation fails after retries
    """
    primitive_id = primitive.get("primitive_id", "unknown")
    primitive_seed = hash_seed(global_seed, primitive_id)
    instance_seed = hash_seed(primitive_seed, index, f"instance")

    for attempt in range(max_retries):
        # Create RNG with varied seed per attempt
        attempt_seed = hash_seed(instance_seed, attempt, f"attempt")
        rng = random.Random(attempt_seed)

        try:
            # Start with primitive defaults
            defaults = primitive.get("defaults", {})
            instance = merge_dicts({}, defaults)

            # Set instance ID
            instance["id"] = generate_instance_id(primitive_id, index)

            # Store metadata
            instance["_primitive_id"] = primitive_id
            instance["_generation_seed"] = attempt_seed

            # Fill in missing placement fields
            fill_missing_placement_fields(instance, rng)

            # Resolve randomization
            variables = resolve_randomization(instance, rng)
            variables.update(resolve_dynamic_template_variables(instance, dynamic_config, variables))

            # Render templates
            render_instance_templates(instance, variables)

            # Validate placement constraints
            validate_placement_constraints(instance)

            # Check constraints
            constraint_checker.check_instance(instance)

            # Create clean instance for validation (no metadata fields)
            clean_instance = {k: v for k, v in instance.items() if not k.startswith("_")}

            # Validate against schema
            validate_instance(clean_instance, schema)

            # Success!
            return instance, attempt_seed

        except (ConstraintViolation, ValueError) as e:
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to generate instance {primitive_id}[{index}] "
                    f"after {max_retries} attempts: {e}"
                )
            # Retry with different seed
            continue

    # Should not reach here
    raise ValueError(f"Failed to generate instance {primitive_id}[{index}]")


def write_instance_files(
    instance: Dict[str, Any],
    output_dir: Path
) -> None:
    """Write instance to output files.

    Creates both .yaml and .resolved.yaml files.

    Args:
        instance: Instance dictionary to write
        output_dir: Output directory
    """
    instance_id = instance["id"]

    # Clean up metadata fields before writing
    clean_instance = {k: v for k, v in instance.items() if not k.startswith("_")}

    # Write .yaml file
    yaml_path = output_dir / f"{instance_id}.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(clean_instance, f, default_flow_style=False, sort_keys=False)

    # Write .resolved.yaml file (identical but marked immutable)
    resolved_path = output_dir / f"{instance_id}.resolved.yaml"
    with open(resolved_path, "w", encoding="utf-8") as f:
        f.write("# RESOLVED INSTANCE - DO NOT EDIT\n")
        f.write("# This file is generated and should be byte-identical across runs\n\n")
        yaml.dump(clean_instance, f, default_flow_style=False, sort_keys=False)


def generate_instances(
    primitives_dir: Path,
    output_dir: Path,
    schema_path: Path,
    global_seed: int = 42,
    instances_per_primitive: int = 20,
    real_solution_routes: Set[str] | None = None,
    challenge_id: str = "example_challenge",
    dynamic_route_style: str = "plausible",
    max_retries: int = 10
) -> List[Tuple[Dict[str, Any], int]]:
    """Generate all instances.

    Args:
        primitives_dir: Directory containing primitive YAML files
        output_dir: Output directory for generated instances
        schema_path: Path to JSON Schema file
        global_seed: Global seed for deterministic generation
        instances_per_primitive: Number of instances to generate per primitive
        real_solution_routes: Set of real solution routes to avoid
        challenge_id: Challenge ID used for deterministic dynamic routes
        dynamic_route_style: Dynamic route style used by runtime registration
        max_retries: Maximum retries per instance

    Returns:
        List of (instance, seed) tuples for manifest
    """
    # Load schema
    print(f"Loading schema from {schema_path}")
    schema = load_json_schema(str(schema_path))

    # Load primitives
    print(f"Loading primitives from {primitives_dir}")
    primitives = load_primitives(primitives_dir)
    print(f"Found {len(primitives)} primitives")

    # Create constraint checker
    constraint_checker = ConstraintChecker(real_solution_routes or set())
    dynamic_config = build_dynamic_generation_config(
        challenge_id=challenge_id,
        route_style=dynamic_route_style,
    )

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate instances
    all_instances = []

    for primitive in primitives:
        primitive_id = primitive.get("primitive_id", "unknown")
        print(f"\nGenerating {instances_per_primitive} instances for {primitive_id}...")

        for i in range(instances_per_primitive):
            try:
                instance, seed = generate_single_instance(
                    primitive,
                    i,
                    global_seed,
                    schema,
                    constraint_checker,
                    dynamic_config,
                    max_retries
                )

                # Write files
                write_instance_files(instance, output_dir)

                # Store for manifest
                all_instances.append((instance, seed))

                if (i + 1) % 5 == 0:
                    print(f"  Generated {i + 1}/{instances_per_primitive}")

            except Exception as e:
                print(f"  ERROR generating instance {i}: {e}", file=sys.stderr)
                raise

    print(f"\n✓ Successfully generated {len(all_instances)} instances")
    return all_instances


def main(argv: List[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command line arguments (None = sys.argv)

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Generate deception instances from primitives"
    )
    parser.add_argument(
        "--primitives-dir",
        type=Path,
        default=Path("deceptions/primitives"),
        help="Directory containing primitive YAML files (default: deceptions/primitives)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("deceptions/instances/generated"),
        help="Output directory for generated instances (default: deceptions/instances/generated)"
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("deceptions/schemas/deception.schema.json"),
        help="Path to JSON Schema file (default: deceptions/schemas/deception.schema.json)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Global seed for deterministic generation (default: 42)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of instances per primitive (default: 20)"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=10,
        help="Maximum retries per instance (default: 10)"
    )
    parser.add_argument(
        "--real-routes",
        type=str,
        help="Comma-separated list of real solution routes to avoid"
    )
    parser.add_argument(
        "--challenge-id",
        type=str,
        default=os.getenv("DECEPTIONS_CHALLENGE_ID", "example_challenge"),
        help="Challenge ID used for deterministic dynamic routes (default: DECEPTIONS_CHALLENGE_ID or example_challenge)"
    )
    parser.add_argument(
        "--dynamic-route-style",
        choices=["namespaced", "plausible"],
        default=os.getenv("DECEPTIONS_DYNAMIC_ROUTE_STYLE", "plausible"),
        help="Dynamic route style to render into templates (default: DECEPTIONS_DYNAMIC_ROUTE_STYLE or plausible)"
    )

    args = parser.parse_args(argv)

    # Parse real routes
    real_routes = set()
    if args.real_routes:
        real_routes = {r.strip() for r in args.real_routes.split(",") if r.strip()}

    try:
        # Generate instances
        instances = generate_instances(
            primitives_dir=args.primitives_dir,
            output_dir=args.output_dir,
            schema_path=args.schema,
            global_seed=args.seed,
            instances_per_primitive=args.count,
            real_solution_routes=real_routes,
            challenge_id=args.challenge_id,
            dynamic_route_style=args.dynamic_route_style,
            max_retries=args.max_retries
        )

        # Create manifest
        manifest_path = args.output_dir / "manifest.jsonl"
        print(f"\nWriting manifest to {manifest_path}")
        create_manifest(instances, str(manifest_path))

        print(f"\n✓ Generation complete!")
        print(f"  Instances: {len(instances)}")
        print(f"  Output: {args.output_dir}")
        print(f"  Manifest: {manifest_path}")

        return 0

    except Exception as e:
        print(f"\n✗ Generation failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
