"""
Deception Runtime for Flask-based CTF Challenges

A reusable package that enables automated deception injection with minimal
code changes to Flask applications.
"""

__version__ = "0.1.0"

from deception_runtime.context import DeceptionContext
from deception_runtime.challenge_setup import configure_trapped_app
from deception_runtime.extension import DeceptionRuntime
from deception_runtime.runtime import (
    get_active_instance,
    get_runtime,
    is_deceptions_enabled,
)

__all__ = [
    "DeceptionContext",
    "DeceptionRuntime",
    "configure_trapped_app",
    "get_active_instance",
    "get_runtime",
    "is_deceptions_enabled",
]
