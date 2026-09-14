"""
Request-scoped deception context.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class DeceptionContext:
    """
    Request-scoped deception context populated by the Flask before_request hook.

    Attributes:
        enabled: Whether deceptions are enabled for this request
        challenge_id: The challenge identifier
        instance_id: The active deception instance ID (if any)
        student_id: The student identifier (if any)
        request_id: Unique request identifier (UUID4)
    """

    enabled: bool
    challenge_id: str
    instance_id: str | None
    student_id: str | None
    request_id: str

    @classmethod
    def create_disabled(cls, challenge_id: str) -> "DeceptionContext":
        """Create a disabled context (no deception active)."""
        return cls(
            enabled=False,
            challenge_id=challenge_id,
            instance_id=None,
            student_id=None,
            request_id=str(uuid.uuid4()),
        )

    @classmethod
    def create_enabled(
        cls,
        challenge_id: str,
        instance_id: str | None,
        student_id: str | None,
    ) -> "DeceptionContext":
        """Create an enabled context with optional instance and student IDs."""
        return cls(
            enabled=True,
            challenge_id=challenge_id,
            instance_id=instance_id,
            student_id=student_id,
            request_id=str(uuid.uuid4()),
        )
