"""
Flask blueprints for honeytoken endpoints and telemetry stats.
"""

from flask import Blueprint, Response, current_app, jsonify, request

from deception_runtime.logging import StructuredLogger
from deception_runtime.trap_pages import endpoint_trap_response

logger = StructuredLogger(__name__)


def create_honeytoken_handler(
    instance_id: str,
    path: str,
    response_mode: int = 200,
):
    """
    Create a Flask view function for a honeytoken endpoint.

    Args:
        instance_id: Instance ID that owns this honeytoken
        path: The honeytoken path
        response_mode: HTTP status code to return (200 or 404)

    Returns:
        View function
    """

    def handle_honeytoken():
        """Handle honeytoken hit."""
        from flask import g

        # Get runtime
        runtime = current_app.extensions.get("deception_runtime")
        if not runtime or not runtime.telemetry:
            # Telemetry not initialized, just return plausible response
            if response_mode == 404:
                return Response("Not Found", status=404, mimetype="text/plain")
            return Response("OK", status=200, mimetype="text/plain")

        # Get context
        ctx = getattr(g, "deception_ctx", None)
        if not ctx:
            # No context, but emit generic event
            request_id = "unknown"
            student_id = None
        else:
            request_id = ctx.request_id
            student_id = ctx.student_id

        # Emit honeytoken_hit event
        try:
            runtime.telemetry.emit(
                event_type="honeytoken_hit",
                request_id=request_id,
                challenge_id=runtime.config.challenge_id,
                route=request.path,
                method=request.method,
                instance_id=instance_id,
                student_id=student_id,
                user_agent=request.headers.get("User-Agent"),
                remote_addr=request.remote_addr,
                extra={
                    "token_type": "url",
                    "matched_path": path,
                    "detected_via": "endpoint",
                },
            )

            logger.info(
                "Honeytoken hit",
                instance_id=instance_id,
                path=path,
                request_id=request_id,
            )
        except Exception as e:
            logger.error("Failed to emit honeytoken_hit event", error=str(e))

        # Endpoint-specific trap pages are additive and only active when enabled.
        if runtime.config.endpoint_traps_enabled and runtime.endpoint_trap_classifier:
            classification = runtime.endpoint_trap_classifier.classify(path)
            return endpoint_trap_response(
                runtime=runtime,
                classification=classification,
                instance_id=instance_id,
                endpoint_path=path,
                interactive=runtime.config.endpoint_traps_interactive,
                max_steps=runtime.config.endpoint_traps_max_steps,
                fake_goal_enabled=runtime.config.endpoint_traps_fake_goals_enabled,
            )

        # Return plausible fallback response.
        if response_mode == 404:
            return Response("Not Found", status=404, mimetype="text/plain")

        html = (
            "<!DOCTYPE html>"
            "<html><head><title>Page</title></head>"
            "<body><h1>Content</h1><p>This is a page.</p></body></html>"
        )
        return Response(html, status=200, mimetype="text/html")

    # Set a unique function name for Flask routing
    handle_honeytoken.__name__ = f"honeytoken_{instance_id}_{abs(hash(path))}"

    return handle_honeytoken


def create_telemetry_stats_blueprint() -> Blueprint:
    """
    Create a blueprint for telemetry statistics endpoint.

    Returns:
        Flask Blueprint
    """
    bp = Blueprint("deception_telemetry", __name__, url_prefix="/__deception__")

    @bp.route("/telemetry_stats", methods=["GET"])
    def telemetry_stats():
        """Return in-memory telemetry statistics."""
        runtime = current_app.extensions.get("deception_runtime")
        if not runtime:
            return jsonify(
                {
                    "status": "error",
                    "message": "Deception runtime not initialized",
                }
            ), 500

        stats = {
            "telemetry_enabled": runtime.config.telemetry_enabled
            if hasattr(runtime.config, "telemetry_enabled")
            else False,
            "honeytokens_enabled": runtime.config.honeytokens_enabled
            if hasattr(runtime.config, "honeytokens_enabled")
            else False,
        }

        # Add honeytoken stats if available
        if hasattr(runtime, "honeytoken_matcher") and runtime.honeytoken_matcher:
            stats["honeytoken_paths"] = len(
                runtime.honeytoken_matcher.path_to_instances
            )
            stats["total_honeytokens"] = len(runtime.honeytoken_matcher.honeytokens)

        return jsonify(stats)

    @bp.route("/honeytokens", methods=["GET"])
    def honeytokens():
        """
        Return list of registered honeytoken paths and mappings.

        This management endpoint lists all URL honeytoken paths that were
        registered at init time and returns a mapping from path -> instance IDs.
        """
        runtime = current_app.extensions.get("deception_runtime")
        if not runtime:
            return jsonify(
                {
                    "status": "error",
                    "message": "Deception runtime not initialized",
                }
            ), 500

        # If honeytokens aren't enabled or matcher not present, return empty result
        if not hasattr(runtime, "honeytoken_matcher") or not runtime.honeytoken_matcher:
            return jsonify(
                {
                    "honeytokens_enabled": False,
                    "paths": [],
                    "mapping": {},
                }
            )

        matcher = runtime.honeytoken_matcher

        # The matcher exposes get_url_paths() and path_to_instances
        try:
            paths = matcher.get_url_paths()
        except Exception:
            # Fallback: derive from internal mapping if available
            paths = list(getattr(matcher, "path_to_instances", {}).keys())

        mapping = {}
        path_to_instances = getattr(matcher, "path_to_instances", {})
        for p in paths:
            mapping[p] = list(path_to_instances.get(p, []))

        return jsonify(
            {
                "honeytokens_enabled": True,
                "paths": paths,
                "mapping": mapping,
                "count": len(paths),
            }
        )

    return bp
