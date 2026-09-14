"""
Telemetry coordinator for event emission and sampling.
"""

import hashlib
from typing import Any

from deception_runtime.events import EventType, create_event, validate_event
from deception_runtime.logging import StructuredLogger
from deception_runtime.sinks import TelemetrySink

logger = StructuredLogger(__name__)


class TelemetryCoordinator:
    """
    Coordinates telemetry event creation, sampling, and emission to sinks.
    """

    def __init__(
        self,
        sink: TelemetrySink,
        sample_rate: float = 1.0,
        validate_events: bool = False,
    ):
        """
        Initialize telemetry coordinator.

        Args:
            sink: Telemetry sink to emit events to
            sample_rate: Sampling rate (0.0 to 1.0)
            validate_events: Whether to validate events before emission
        """
        self.sink = sink
        self.sample_rate = max(0.0, min(1.0, sample_rate))
        self.validate_events = validate_events

        logger.info(
            "Telemetry coordinator initialized",
            sample_rate=self.sample_rate,
            validate=self.validate_events,
        )

    def _should_sample(self, request_id: str) -> bool:
        """
        Determine if request should be sampled.

        Uses deterministic hashing of request_id for consistent sampling.

        Args:
            request_id: Request identifier

        Returns:
            True if request should be sampled
        """
        if self.sample_rate >= 1.0:
            return True
        if self.sample_rate <= 0.0:
            return False

        # Deterministic sampling based on request_id hash
        hash_value = int(hashlib.sha256(request_id.encode()).hexdigest()[:8], 16)
        threshold = int(0xFFFFFFFF * self.sample_rate)

        return hash_value <= threshold

    def emit(
        self,
        event: dict[str, Any] | None = None,
        event_type: EventType | None = None,
        request_id: str | None = None,
        challenge_id: str | None = None,
        route: str | None = None,
        method: str | None = None,
        instance_id: str | None = None,
        student_id: str | None = None,
        status_code: int | None = None,
        user_agent: str | None = None,
        remote_addr: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """
        Emit a telemetry event.

        This method accepts either:
          - a pre-built event dictionary passed as the first positional argument, e.g.:
                telemetry.emit(event_dict)
          - or individual event fields as keyword arguments, e.g.:
                telemetry.emit(event_type="request_start", request_id="...", ...)

        Sampling is performed based on the `request_id` found in the final event.
        If `request_id` is missing from a pre-built event or omitted when using
        individual params, the event will be skipped (sampling requires request_id).

        Args:
            event: Optional pre-built event dict. If provided, other params are ignored.
            event_type: Type of event (when `event` is not provided)
            request_id: Unique request ID (when `event` is not provided)
            challenge_id: Challenge identifier (when `event` is not provided)
            route: Request path (when `event` is not provided)
            method: HTTP method (when `event` is not provided)
            instance_id: Active deception instance ID
            student_id: Student identifier
            status_code: HTTP status code
            user_agent: User-Agent header
            remote_addr: Client IP address
            extra: Additional event data
        """
        # Determine final event dict: either use provided dict or build one from params
        if event is not None:
            if not isinstance(event, dict):
                logger.warning(
                    "Telemetry emit called with non-dict first argument; skipping"
                )
                return
            final_event = event
        else:
            # Ensure required fields are present when building an event
            missing = []
            if event_type is None:
                missing.append("event_type")
            if request_id is None:
                missing.append("request_id")
            if challenge_id is None:
                missing.append("challenge_id")
            if route is None:
                missing.append("route")
            if method is None:
                missing.append("method")

            if missing:
                logger.warning(
                    "Telemetry emit missing required fields; skipping emission",
                    missing=",".join(missing),
                )
                return

            # Assert required fields are non-None so the call to create_event
            # satisfies the type checker and to fail fast at runtime if logic is wrong.
            assert (
                event_type is not None
                and request_id is not None
                and challenge_id is not None
                and route is not None
                and method is not None
            )

            final_event = create_event(
                event_type=event_type,
                request_id=request_id,
                challenge_id=challenge_id,
                route=route,
                method=method,
                instance_id=instance_id,
                student_id=student_id,
                status_code=status_code,
                user_agent=user_agent,
                remote_addr=remote_addr,
                extra=extra,
            )

        # Sampling requires a request_id present in the event
        event_type_val = final_event.get("event_type")
        rid = final_event.get("request_id")
        if not isinstance(rid, str):
            logger.debug(
                "Telemetry event missing request_id; skipping sampling/emission"
            )
            return

        # Always emit honeytoken_hit events regardless of sampling policy so
        # honeytokens are reliably detected and logged.
        if event_type_val == "honeytoken_hit":
            logger.debug(
                "Bypassing sampling for honeytoken_hit event",
                event_type=event_type_val,
                request_id=rid,
            )
        else:
            if not self._should_sample(rid):
                logger.debug(
                    "Event sampled out by sampling policy",
                    event_type=event_type_val,
                    request_id=rid,
                    sample_rate=self.sample_rate,
                )
                return

        # Validate if enabled
        if self.validate_events:
            if not validate_event(final_event, strict=False):
                logger.warning(
                    "Invalid event, skipping emission",
                    event_type=final_event.get("event_type"),
                )
                return

        # Emit to sink
        try:
            self.sink.emit(final_event)
            # Try to flush immediately so tests / external inspection see the event on disk.
            try:
                self.sink.flush()
            except Exception:
                # Not fatal; log at debug level so it's visible during troubleshooting.
                logger.debug(
                    "Sink flush not supported or failed",
                    event_type=final_event.get("event_type"),
                    request_id=final_event.get("request_id"),
                )
            logger.debug(
                "Telemetry event emitted",
                event_type=final_event.get("event_type"),
                request_id=final_event.get("request_id"),
            )
        except Exception as e:
            logger.error(
                "Failed to emit event",
                event_type=final_event.get("event_type"),
                error=str(e),
            )

    def flush(self) -> None:
        """Flush the sink."""
        try:
            self.sink.flush()
        except Exception as e:
            logger.error("Failed to flush sink", error=str(e))

    def close(self) -> None:
        """Close the sink."""
        try:
            self.sink.close()
        except Exception as e:
            logger.error("Failed to close sink", error=str(e))
