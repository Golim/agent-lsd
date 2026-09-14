"""
Configuration management for deception runtime.
"""

import os
from dataclasses import dataclass
from typing import Any


def str_to_bool(value: str | bool | None) -> bool:
    """Convert string to boolean (case-insensitive)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ("true", "1", "yes", "on")


def normalize_route_prefix(prefix: str | None, default: str = "/_deception") -> str:
    """Normalize a URL prefix to a leading-slash, no-trailing-slash format."""
    value = (prefix or "").strip() or default
    if not value.startswith("/"):
        value = f"/{value}"
    if len(value) > 1 and value.endswith("/"):
        value = value[:-1]
    return value


def normalize_fake_goal_mode(value: str | None, default: str = "both") -> str:
    """Normalize fake-goal mode to one of: flag, success_message, both."""
    allowed = {"flag", "success_message", "both"}
    mode = (value or default).strip().lower()
    return mode if mode in allowed else default


def normalize_dynamic_route_style(value: str | None, default: str = "namespaced") -> str:
    """Normalize dynamic route style to one of: namespaced, plausible."""
    allowed = {"namespaced", "plausible"}
    style = (value or default).strip().lower()
    return style if style in allowed else default


@dataclass
class DeceptionConfig:
    """
    Configuration for deception runtime.

    Attributes:
        enabled: Whether deceptions are enabled globally
        instances_dir: Directory containing resolved instance YAML files
        schema_path: Path to deception JSON schema
        instance_header: HTTP header name for instance ID
        instance_query: Query parameter name for instance ID
        student_header: HTTP header name for student ID
        student_cookie: Cookie name for student ID
        challenge_id: Challenge identifier
        fail_closed: Return 400 if instance_id provided but not found

        # Telemetry config
        telemetry_enabled: Whether telemetry is enabled
        telemetry_sink: Type of telemetry sink ('jsonl' or 'sqlite')
        telemetry_path: Path for telemetry storage
        telemetry_fsync: Whether to fsync after writes (JSONL only)
        telemetry_sample_rate: Sampling rate (0.0 to 1.0)

        # Honeytoken config
        honeytokens_enabled: Whether honeytokens are enabled
        honeytoken_response_mode: HTTP status for honeytoken endpoints (200 or 404)
        honeytoken_param: Query parameter name for honeytokens
        honeytoken_header: Header name for honeytokens
        honeytoken_cookie: Cookie name for honeytokens
        honeytoken_value_prefix: Expected value prefix
        protected_routes: List of real routes to avoid overriding

        # Application config
        apply_enabled: Whether to apply deceptions to responses
        apply_fail_open: Return original response on application errors
        apply_max_bytes: Maximum response size to process (bytes)
        apply_allowed_routes: List of routes where deceptions can be applied
        apply_allowed_methods: List of HTTP methods where deceptions can be applied

        # Dynamic deception config
        dynamic_enabled: Enable dynamic deception route families
        dynamic_rabbit_holes_enabled: Enable rabbit-hole dynamic routes
        dynamic_fake_goals_enabled: Enable fake-goal dynamic routes
        dynamic_route_prefix: URL namespace for dynamic deception routes
        dynamic_rabbit_max_depth: Upper bound for rabbit-hole depth
        dynamic_rabbit_max_branching: Upper bound for rabbit-hole branching
        dynamic_fake_goal_mode: Default fake-goal rendering mode
        dynamic_route_style: Route family style (`namespaced` or `plausible`)
        dynamic_fail_open: Continue initialization if dynamic route collision occurs
        dynamic_register_blueprint: Register dynamic routes through Flask blueprint

        # Endpoint trap settings
        endpoint_traps_enabled: Enable endpoint-specific trap page rendering
        endpoint_traps_interactive: Enable bounded interactive step flows
        endpoint_traps_max_steps: Upper bound for endpoint trap step progression
        endpoint_traps_fake_goals_enabled: Allow terminal fake-goal state in endpoint traps
        endpoint_traps_rabbit_holes_enabled: Allow rabbit-hole routes to render endpoint traps
        endpoint_trap_map_file: Optional JSON file for explicit path -> trap_type mapping
        endpoint_traps_opaque_patterns: Optional regex patterns for opaque endpoint classification
    """

    enabled: bool
    instances_dir: str
    schema_path: str
    instance_header: str
    instance_query: str
    student_header: str
    student_cookie: str
    challenge_id: str
    fail_closed: bool

    # Telemetry
    telemetry_enabled: bool
    telemetry_sink: str
    telemetry_path: str
    telemetry_fsync: bool
    telemetry_sample_rate: float

    # Honeytokens
    honeytokens_enabled: bool
    honeytoken_response_mode: int
    honeytoken_param: str
    honeytoken_header: str
    honeytoken_cookie: str
    honeytoken_value_prefix: str
    protected_routes: list[str]

    # Application settings
    apply_enabled: bool
    apply_fail_open: bool
    apply_max_bytes: int
    apply_allowed_routes: list[str]
    apply_allowed_methods: list[str]

    # Dynamic deception settings
    dynamic_enabled: bool
    dynamic_rabbit_holes_enabled: bool
    dynamic_fake_goals_enabled: bool
    dynamic_route_prefix: str
    dynamic_rabbit_max_depth: int
    dynamic_rabbit_max_branching: int
    dynamic_fake_goal_mode: str
    dynamic_route_style: str
    dynamic_fail_open: bool
    dynamic_register_blueprint: bool

    # Endpoint trap settings
    endpoint_traps_enabled: bool
    endpoint_traps_interactive: bool
    endpoint_traps_max_steps: int
    endpoint_traps_fake_goals_enabled: bool
    endpoint_traps_rabbit_holes_enabled: bool
    endpoint_trap_map_file: str
    endpoint_traps_opaque_patterns: list[str]

    @classmethod
    def from_flask_config(cls, app_config: dict[str, Any], app_name: str) -> "DeceptionConfig":
        """
        Load configuration from Flask app.config with environment variable fallbacks.

        Args:
            app_config: Flask app.config dictionary
            app_name: Flask app.name for default challenge_id

        Returns:
            DeceptionConfig instance
        """
        # Parse protected routes (comma-separated)
        protected_routes_str = app_config.get(
            "DECEPTIONS_PROTECTED_ROUTES",
            os.getenv("DECEPTIONS_PROTECTED_ROUTES", ""),
        )
        protected_routes = [r.strip() for r in protected_routes_str.split(",") if r.strip()]
        opaque_patterns_str = app_config.get(
            "DECEPTIONS_ENDPOINT_TRAPS_OPAQUE_PATTERNS",
            os.getenv("DECEPTIONS_ENDPOINT_TRAPS_OPAQUE_PATTERNS", ""),
        )
        opaque_patterns = [p.strip() for p in opaque_patterns_str.split(",") if p.strip()]

        return cls(
            enabled=str_to_bool(
                app_config.get("DECEPTIONS_ENABLED", os.getenv("DECEPTIONS_ENABLED", "false"))
            ),
            instances_dir=app_config.get(
                "DECEPTIONS_INSTANCES_DIR",
                os.getenv("DECEPTIONS_INSTANCES_DIR", "deceptions/instances/generated"),
            ),
            schema_path=app_config.get(
                "DECEPTIONS_SCHEMA_PATH",
                os.getenv("DECEPTIONS_SCHEMA_PATH", "deceptions/schemas/deception.schema.json"),
            ),
            instance_header=app_config.get(
                "DECEPTIONS_INSTANCE_HEADER",
                os.getenv("DECEPTIONS_INSTANCE_HEADER", "X-Instance-Id"),
            ),
            instance_query=app_config.get(
                "DECEPTIONS_INSTANCE_QUERY",
                os.getenv("DECEPTIONS_INSTANCE_QUERY", "instance"),
            ),
            student_header=app_config.get(
                "DECEPTIONS_STUDENT_HEADER",
                os.getenv("DECEPTIONS_STUDENT_HEADER", "X-Student-Id"),
            ),
            student_cookie=app_config.get(
                "DECEPTIONS_STUDENT_COOKIE",
                os.getenv("DECEPTIONS_STUDENT_COOKIE", "student_id"),
            ),
            challenge_id=app_config.get(
                "DECEPTIONS_CHALLENGE_ID",
                os.getenv("DECEPTIONS_CHALLENGE_ID", app_name),
            ),
            fail_closed=str_to_bool(
                app_config.get("DECEPTIONS_FAIL_CLOSED", os.getenv("DECEPTIONS_FAIL_CLOSED", "true"))
            ),
            # Telemetry config
            telemetry_enabled=str_to_bool(
                app_config.get("DECEPTIONS_TELEMETRY_ENABLED", os.getenv("DECEPTIONS_TELEMETRY_ENABLED", "true"))
            ),
            telemetry_sink=app_config.get(
                "DECEPTIONS_TELEMETRY_SINK",
                os.getenv("DECEPTIONS_TELEMETRY_SINK", "jsonl"),
            ),
            telemetry_path=app_config.get(
                "DECEPTIONS_TELEMETRY_PATH",
                os.getenv(
                    "DECEPTIONS_TELEMETRY_PATH",
                    "verification/telemetry.jsonl"
                    if app_config.get("DECEPTIONS_TELEMETRY_SINK", "jsonl") == "jsonl"
                    else "data/telemetry.sqlite",
                ),
            ),
            telemetry_fsync=str_to_bool(
                app_config.get("DECEPTIONS_TELEMETRY_FSYNC", os.getenv("DECEPTIONS_TELEMETRY_FSYNC", "false"))
            ),
            telemetry_sample_rate=float(
                app_config.get("DECEPTIONS_TELEMETRY_SAMPLE_RATE", os.getenv("DECEPTIONS_TELEMETRY_SAMPLE_RATE", "1.0"))
            ),
            # Honeytoken config
            honeytokens_enabled=str_to_bool(
                app_config.get("DECEPTIONS_HONEYTOKENS_ENABLED", os.getenv("DECEPTIONS_HONEYTOKENS_ENABLED", "true"))
            ),
            honeytoken_response_mode=int(
                app_config.get("DECEPTIONS_HONEYTOKEN_RESPONSE_MODE", os.getenv("DECEPTIONS_HONEYTOKEN_RESPONSE_MODE", "200"))
            ),
            honeytoken_param=app_config.get(
                "DECEPTIONS_HONEYTOKEN_PARAM",
                os.getenv("DECEPTIONS_HONEYTOKEN_PARAM", "ht"),
            ),
            honeytoken_header=app_config.get(
                "DECEPTIONS_HONEYTOKEN_HEADER",
                os.getenv("DECEPTIONS_HONEYTOKEN_HEADER", "X-Honeytoken"),
            ),
            honeytoken_cookie=app_config.get(
                "DECEPTIONS_HONEYTOKEN_COOKIE",
                os.getenv("DECEPTIONS_HONEYTOKEN_COOKIE", "ht"),
            ),
            honeytoken_value_prefix=app_config.get(
                "DECEPTIONS_HONEYTOKEN_VALUE_PREFIX",
                os.getenv("DECEPTIONS_HONEYTOKEN_VALUE_PREFIX", ""),
            ),
            protected_routes=protected_routes,
            # Application config
            apply_enabled=str_to_bool(
                app_config.get("DECEPTIONS_APPLY_ENABLED", os.getenv("DECEPTIONS_APPLY_ENABLED", "true"))
            ),
            apply_fail_open=str_to_bool(
                app_config.get("DECEPTIONS_FAIL_OPEN", os.getenv("DECEPTIONS_FAIL_OPEN", "true"))
            ),
            apply_max_bytes=int(
                app_config.get("DECEPTIONS_MAX_BYTES", os.getenv("DECEPTIONS_MAX_BYTES", "2000000"))
            ),
            apply_allowed_routes=[
                r.strip() for r in
                app_config.get(
                    "DECEPTIONS_ALLOWED_ROUTES",
                    os.getenv("DECEPTIONS_ALLOWED_ROUTES", "")
                ).split(",") if r.strip()
            ],
            apply_allowed_methods=[
                m.strip().upper() for m in
                app_config.get(
                    "DECEPTIONS_APPLY_TO_METHODS",
                    os.getenv("DECEPTIONS_APPLY_TO_METHODS", "GET")
                ).split(",") if m.strip()
            ],
            # Dynamic deception config
            dynamic_enabled=str_to_bool(
                app_config.get("DECEPTIONS_DYNAMIC_ENABLED", os.getenv("DECEPTIONS_DYNAMIC_ENABLED", "false"))
            ),
            dynamic_rabbit_holes_enabled=str_to_bool(
                app_config.get(
                    "DECEPTIONS_RABBIT_HOLES_ENABLED",
                    os.getenv("DECEPTIONS_RABBIT_HOLES_ENABLED", "false"),
                )
            ),
            dynamic_fake_goals_enabled=str_to_bool(
                app_config.get(
                    "DECEPTIONS_FAKE_GOALS_ENABLED",
                    os.getenv("DECEPTIONS_FAKE_GOALS_ENABLED", "false"),
                )
            ),
            dynamic_route_prefix=normalize_route_prefix(
                app_config.get(
                    "DECEPTIONS_DYNAMIC_ROUTE_PREFIX",
                    os.getenv("DECEPTIONS_DYNAMIC_ROUTE_PREFIX", "/_deception"),
                )
            ),
            dynamic_rabbit_max_depth=max(
                1,
                int(
                    app_config.get(
                        "DECEPTIONS_RABBIT_MAX_DEPTH",
                        os.getenv("DECEPTIONS_RABBIT_MAX_DEPTH", "3"),
                    )
                ),
            ),
            dynamic_rabbit_max_branching=max(
                1,
                int(
                    app_config.get(
                        "DECEPTIONS_RABBIT_MAX_BRANCHING",
                        os.getenv("DECEPTIONS_RABBIT_MAX_BRANCHING", "1"),
                    )
                ),
            ),
            dynamic_fake_goal_mode=normalize_fake_goal_mode(
                app_config.get(
                    "DECEPTIONS_FAKE_GOAL_MODE",
                    os.getenv("DECEPTIONS_FAKE_GOAL_MODE", "both"),
                )
            ),
            dynamic_route_style=normalize_dynamic_route_style(
                app_config.get(
                    "DECEPTIONS_DYNAMIC_ROUTE_STYLE",
                    os.getenv("DECEPTIONS_DYNAMIC_ROUTE_STYLE", "namespaced"),
                )
            ),
            dynamic_fail_open=str_to_bool(
                app_config.get(
                    "DECEPTIONS_DYNAMIC_FAIL_OPEN",
                    os.getenv("DECEPTIONS_DYNAMIC_FAIL_OPEN", "true"),
                )
            ),
            dynamic_register_blueprint=str_to_bool(
                app_config.get(
                    "DECEPTIONS_DYNAMIC_REGISTER_BLUEPRINT",
                    os.getenv("DECEPTIONS_DYNAMIC_REGISTER_BLUEPRINT", "true"),
                )
            ),
            # Endpoint trap settings
            endpoint_traps_enabled=str_to_bool(
                app_config.get(
                    "DECEPTIONS_ENDPOINT_TRAPS_ENABLED",
                    os.getenv("DECEPTIONS_ENDPOINT_TRAPS_ENABLED", "false"),
                )
            ),
            endpoint_traps_interactive=str_to_bool(
                app_config.get(
                    "DECEPTIONS_ENDPOINT_TRAPS_INTERACTIVE",
                    os.getenv("DECEPTIONS_ENDPOINT_TRAPS_INTERACTIVE", "false"),
                )
            ),
            endpoint_traps_max_steps=max(
                0,
                int(
                    app_config.get(
                        "DECEPTIONS_ENDPOINT_TRAPS_MAX_STEPS",
                        os.getenv("DECEPTIONS_ENDPOINT_TRAPS_MAX_STEPS", "2"),
                    )
                ),
            ),
            endpoint_traps_fake_goals_enabled=str_to_bool(
                app_config.get(
                    "DECEPTIONS_ENDPOINT_TRAPS_FAKE_GOALS_ENABLED",
                    os.getenv("DECEPTIONS_ENDPOINT_TRAPS_FAKE_GOALS_ENABLED", "false"),
                )
            ),
            endpoint_traps_rabbit_holes_enabled=str_to_bool(
                app_config.get(
                    "DECEPTIONS_ENDPOINT_TRAPS_RABBIT_HOLES_ENABLED",
                    os.getenv("DECEPTIONS_ENDPOINT_TRAPS_RABBIT_HOLES_ENABLED", "false"),
                )
            ),
            endpoint_trap_map_file=app_config.get(
                "DECEPTIONS_ENDPOINT_TRAP_MAP_FILE",
                os.getenv("DECEPTIONS_ENDPOINT_TRAP_MAP_FILE", ""),
            ),
            endpoint_traps_opaque_patterns=opaque_patterns,
        )
