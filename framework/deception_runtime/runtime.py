"""
Runtime helpers for accessing active deception context and instances.
"""

from flask import Flask, current_app, g

from deception_runtime.context import DeceptionContext
from deception_runtime.registry import DeceptionInstance


def get_runtime(app: Flask | None = None):
    """
    Get the DeceptionRuntime extension instance.

    Args:
        app: Flask app (uses current_app if not provided)

    Returns:
        DeceptionRuntime instance

    Raises:
        RuntimeError: If extension not initialized
    """
    if app is None:
        app = current_app

    runtime = app.extensions.get("deception_runtime")
    if not runtime:
        raise RuntimeError(
            "DeceptionRuntime extension not initialized. "
            "Call DeceptionRuntime().init_app(app) first."
        )

    return runtime


def get_active_instance() -> DeceptionInstance | None:
    """
    Get the active deception instance for the current request.

    Returns:
        DeceptionInstance if one is active, None otherwise

    Raises:
        RuntimeError: If called outside request context or extension not initialized
    """
    # Check if we have a context
    ctx: DeceptionContext | None = getattr(g, "deception_ctx", None)

    if not ctx:
        raise RuntimeError(
            "No deception context found. "
            "Ensure DeceptionRuntime is initialized and called within request context."
        )

    # If deceptions disabled or no instance_id, return None
    if not ctx.enabled or not ctx.instance_id:
        return None

    # Get runtime and registry
    runtime = get_runtime()

    if not runtime.registry:
        return None

    # Fetch instance from registry
    return runtime.registry.get(ctx.instance_id)


def is_deceptions_enabled() -> bool:
    """
    Check if deceptions are enabled for the current request.

    Returns:
        True if deceptions are enabled and an instance is active

    Raises:
        RuntimeError: If called outside request context
    """
    ctx: DeceptionContext | None = getattr(g, "deception_ctx", None)

    if not ctx:
        raise RuntimeError(
            "No deception context found. "
            "Ensure DeceptionRuntime is initialized and called within request context."
        )

    return ctx.enabled and ctx.instance_id is not None
