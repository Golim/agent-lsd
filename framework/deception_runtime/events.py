"""
Telemetry event definitions and creation.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from deception_runtime.logging import StructuredLogger

logger = StructuredLogger(__name__)

# Event type constants
EventType = Literal[
    "request_start",
    "request_end",
    "instance_selected",
    "honeytoken_hit",
    "deception_rendered",
    "deception_interacted",
    "deception_apply_failed",
    "rabbit_hole_entered",
    "rabbit_hole_hop",
    "rabbit_hole_terminal",
    "fake_goal_viewed",
    "fake_goal_flag_shown",
    "fake_goal_success_shown",
    "endpoint_trap_viewed",
    "endpoint_trap_step",
    "endpoint_trap_action",
    "endpoint_trap_terminal",
]

# Load schema if available
_SCHEMA: dict[str, Any] | None = None


def _load_schema() -> dict[str, Any] | None:
    """Load event schema from JSON file."""
    global _SCHEMA
    if _SCHEMA is not None:
        return _SCHEMA

    schema_path = Path(__file__).parent / "schemas" / "telemetry_event.schema.json"
    if not schema_path.exists():
        logger.warning("Telemetry event schema not found", path=str(schema_path))
        return None

    try:
        with open(schema_path) as f:
            _SCHEMA = json.load(f)
        return _SCHEMA
    except Exception as e:
        logger.warning("Failed to load telemetry event schema", error=str(e))
        return None


def create_event(
    event_type: EventType,
    request_id: str,
    challenge_id: str,
    route: str,
    method: str,
    instance_id: str | None = None,
    student_id: str | None = None,
    status_code: int | None = None,
    user_agent: str | None = None,
    remote_addr: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a telemetry event.

    Args:
        event_type: Type of event
        request_id: Unique request ID (UUID4)
        challenge_id: Challenge identifier
        route: Request path
        method: HTTP method
        instance_id: Active deception instance ID
        student_id: Student identifier
        status_code: HTTP status code
        user_agent: User-Agent header
        remote_addr: Client IP address
        extra: Additional event-specific data

    Returns:
        Event dictionary
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "request_id": request_id,
        "challenge_id": challenge_id,
        "instance_id": instance_id,
        "student_id": student_id,
        "route": route,
        "method": method,
        "status_code": status_code,
        "user_agent": user_agent,
        "remote_addr": remote_addr,
        "extra": extra or {},
    }

    return event


def validate_event(event: dict[str, Any], strict: bool = False) -> bool:
    """
    Validate a telemetry event.

    Args:
        event: Event dictionary
        strict: Use JSON schema validation if available

    Returns:
        True if valid, False otherwise
    """
    # Basic validation
    required_fields = [
        "timestamp",
        "event_type",
        "request_id",
        "challenge_id",
        "route",
        "method",
    ]

    for field in required_fields:
        if field not in event:
            logger.warning("Event missing required field", field=field)
            return False

    # Validate event_type
    valid_types = {
        "request_start",
        "request_end",
        "instance_selected",
        "honeytoken_hit",
        "deception_rendered",
        "deception_interacted",
        "deception_apply_failed",
        "rabbit_hole_entered",
        "rabbit_hole_hop",
        "rabbit_hole_terminal",
        "fake_goal_viewed",
        "fake_goal_flag_shown",
        "fake_goal_success_shown",
        "endpoint_trap_viewed",
        "endpoint_trap_step",
        "endpoint_trap_action",
        "endpoint_trap_terminal",
    }
    if event["event_type"] not in valid_types:
        logger.warning("Invalid event_type", event_type=event["event_type"])
        return False

    # Schema validation if strict and available
    if strict:
        try:
            import jsonschema

            schema = _load_schema()
            if schema:
                jsonschema.validate(instance=event, schema=schema)
        except ImportError:
            # jsonschema not available, skip strict validation
            pass
        except Exception as e:
            logger.warning("Event schema validation failed", error=str(e))
            return False

    return True
