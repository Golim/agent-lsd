"""
Main orchestration for deception application.
"""

import hashlib
from typing import Any

from flask import Response, g

from deception_runtime.dom_apply import apply_dom
from deception_runtime.errors import ContentTooLargeError, DeceptionApplicationError
from deception_runtime.html_tools import check_html_parser_available
from deception_runtime.logging import StructuredLogger
from deception_runtime.pixel_apply import apply_pixel
from deception_runtime.registry import DeceptionInstance

logger = StructuredLogger(__name__)


def compute_payload_hash(payload: str) -> str:
    """
    Compute SHA-256 hash of payload for telemetry.

    Args:
        payload: Payload text

    Returns:
        Hex digest of SHA-256 hash
    """
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def is_eligible_response(response: Response, config: dict) -> tuple[bool, str | None]:
    """
    Check if response is eligible for deception application.

    Args:
        response: Flask response object
        config: Configuration dict

    Returns:
        (eligible, reason) tuple
    """
    # Check status code (only 2xx and 3xx)
    if not (200 <= response.status_code < 400):
        return False, f"status code {response.status_code}"

    # Check Content-Type
    content_type = response.content_type or ""
    if not content_type.startswith("text/html"):
        return False, f"content type {content_type}"

    # Check if response has data
    if not response.data:
        return False, "empty response"

    # Check size limit
    max_bytes = config.get("max_bytes", 2_000_000)
    if len(response.data) > max_bytes:
        return False, f"response too large ({len(response.data)} > {max_bytes})"

    # Check if streaming
    if response.is_streamed:
        return False, "streaming response"

    # Check if already compressed
    if response.headers.get("Content-Encoding"):
        return False, f"already encoded ({response.headers.get('Content-Encoding')})"

    return True, None


def is_route_allowed(request_path: str, instance: DeceptionInstance, config: dict) -> bool:
    """
    Check if deception should be applied to this route.

    Args:
        request_path: Request path
        instance: Deception instance
        config: Configuration dict

    Returns:
        True if route is allowed
    """
    placement = instance.placement or {}
    instance_route = placement.get("route")

    # If instance specifies a route, check exact match
    if instance_route:
        if request_path != instance_route:
            logger.debug(
                "Route mismatch",
                request_path=request_path,
                instance_route=instance_route,
                instance_id=instance.instance_id
            )
            return False
    else:
        # Check against allowed routes from config
        allowed_routes = config.get("allowed_routes", [])
        if allowed_routes and request_path not in allowed_routes:
            logger.debug(
                "Route not in allowed list",
                request_path=request_path,
                allowed_routes=allowed_routes,
                instance_id=instance.instance_id
            )
            return False

    return True


def apply_deceptions_to_response(response: Response, runtime: Any, config: dict) -> Response:
    """
    Apply deceptions to Flask response.

    This is the main entry point called from after_request hook.

    Args:
        response: Flask response object
        runtime: DeceptionRuntime instance
        config: Configuration dict with:
            - enabled: bool
            - apply_enabled: bool
            - fail_open: bool
            - max_bytes: int
            - allowed_routes: list
            - allowed_methods: list

    Returns:
        Modified or original response
    """
    # Quick checks
    if not config.get("enabled", False):
        return response

    if not config.get("apply_enabled", True):
        return response

    # Check deception context
    ctx = getattr(g, "deception_ctx", None)
    if not ctx or not ctx.enabled or not ctx.instance_id:
        return response

    # Check request method
    from flask import request
    allowed_methods = config.get("allowed_methods", ["GET"])
    if request.method not in allowed_methods:
        logger.debug(
            "Method not allowed for deception application",
            method=request.method,
            allowed_methods=allowed_methods
        )
        return response

    # Check response eligibility
    eligible, reason = is_eligible_response(response, config)
    if not eligible:
        logger.debug(
            "Response not eligible for deception application",
            reason=reason,
            instance_id=ctx.instance_id
        )
        return response

    try:
        # Get instance from registry
        if not runtime or not runtime.registry:
            logger.warning("No registry available")
            return response

        instance = runtime.registry.get(ctx.instance_id)
        if not instance:
            logger.warning(
                "Instance not found in registry",
                instance_id=ctx.instance_id
            )
            return response

        # Check route gating
        if not is_route_allowed(request.path, instance, config):
            return response

        # Check HTML parser availability
        check_html_parser_available()

        # Get original HTML
        html = response.data.decode("utf-8", errors="replace")
        modified_html = html

        # Apply based on channel
        channel = instance.raw.get("perception", {}).get("channel", "")
        channel_type = channel.split(".")[0] if "." in channel else channel
        is_robots_txt = request.path.rstrip("/") == "/robots.txt"

        applied = False

        if channel_type == "dom":
            logger.debug(
                "Applying DOM deception",
                instance_id=instance.instance_id,
                surface=instance.surface
            )
            modified_html = apply_dom(
                modified_html, instance, config,
                robots_txt=is_robots_txt
            )
            applied = True

        elif channel_type == "pixel":
            logger.debug(
                "Applying pixel deception",
                instance_id=instance.instance_id,
                surface=instance.surface
            )
            modified_html = apply_pixel(modified_html, instance, config)
            applied = True

        elif channel_type == "hybrid":
            # Apply both DOM and pixel
            logger.debug(
                "Applying hybrid deception",
                instance_id=instance.instance_id,
                surface=instance.surface
            )
            # Try DOM first
            try:
                modified_html = apply_dom(
                    modified_html, instance, config,
                    robots_txt=is_robots_txt
                )
            except Exception as e:
                logger.warning(
                    "DOM application failed in hybrid mode",
                    error=str(e)
                )

            # Then pixel
            try:
                modified_html = apply_pixel(modified_html, instance, config)
            except Exception as e:
                logger.warning(
                    "Pixel application failed in hybrid mode",
                    error=str(e)
                )

            applied = True

        else:
            logger.warning(
                "Unsupported channel type",
                channel=channel,
                instance_id=instance.instance_id
            )
            return response

        # Update response if modified
        if applied and modified_html != html:
            response.data = modified_html.encode("utf-8")

            # Update Content-Length
            if "Content-Length" in response.headers:
                response.headers["Content-Length"] = str(len(response.data))

            # Emit telemetry
            if runtime.telemetry:
                try:
                    from deception_runtime.events import create_event

                    placement = instance.placement or {}
                    payload_hash = compute_payload_hash(instance.payload_text or "")

                    event = create_event(
                        event_type="deception_rendered",
                        request_id=ctx.request_id,
                        challenge_id=ctx.challenge_id,
                        route=request.path,
                        method=request.method,
                        instance_id=instance.instance_id,
                        student_id=ctx.student_id,
                        extra={
                            "channel": channel,
                            "surface": instance.surface,
                            "selector": placement.get("selector"),
                            "canvas_id": placement.get("canvas_id"),
                            "payload_hash": payload_hash,
                        }
                    )

                    runtime.telemetry.emit(event)
                except Exception as e:
                    logger.warning("Failed to emit telemetry", error=str(e))

            logger.info(
                "Deception applied successfully",
                instance_id=instance.instance_id,
                channel=channel,
                surface=instance.surface,
                original_size=len(html),
                modified_size=len(modified_html)
            )

        return response

    except DeceptionApplicationError as e:
        # Known deception errors
        logger.warning(
            "Deception application failed",
            instance_id=ctx.instance_id,
            error=str(e),
            safe=e.safe
        )

        # Emit failure telemetry
        if runtime and runtime.telemetry:
            try:
                from deception_runtime.events import create_event

                event = create_event(
                    event_type="deception_apply_failed",
                    request_id=ctx.request_id,
                    challenge_id=ctx.challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=ctx.instance_id,
                    student_id=ctx.student_id,
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

                runtime.telemetry.emit(event)
            except Exception:
                pass

        if config.get("fail_open", True):
            return response
        else:
            # Fail closed: abort with 500
            from flask import abort
            abort(500, description=f"Deception application failed: {e}")

    except Exception as e:
        # Unexpected errors
        logger.exception(
            "Unexpected error during deception application",
            instance_id=ctx.instance_id,
            error=str(e)
        )

        if config.get("fail_open", True):
            return response
        else:
            from flask import abort
            abort(500, description="Deception application failed")
