"""
Shared Flask challenge bootstrap for the deception runtime.
"""

from flask import Flask

from deception_runtime.extension import DeceptionRuntime


def configure_trapped_app(app: Flask, challenge_id: str) -> DeceptionRuntime:
    """
    Apply the default deception settings used by the challenge apps.

    Args:
        app: Flask application to configure
        challenge_id: Unique challenge identifier used for telemetry and routing

    Returns:
        Initialised DeceptionRuntime instance
    """
    app.config["DECEPTIONS_ENABLED"] = True
    app.config["DECEPTIONS_INSTANCES_DIR"] = "deceptions/instances/generated"
    app.config["DECEPTIONS_CHALLENGE_ID"] = challenge_id
    app.config["DECEPTIONS_APPLY_ENABLED"] = True
    app.config["DECEPTIONS_ALLOWED_ROUTES"] = ""
    app.config["DECEPTIONS_APPLY_TO_METHODS"] = "GET"

    app.config["DECEPTIONS_TELEMETRY_ENABLED"] = True
    app.config["DECEPTIONS_TELEMETRY_SINK"] = "jsonl"
    app.config["DECEPTIONS_TELEMETRY_PATH"] = f"/tmp/deception_telemetry/{challenge_id}.jsonl"
    app.config["DECEPTIONS_HONEYTOKENS_ENABLED"] = True
    app.config["DECEPTIONS_TELEMETRY_SAMPLE_RATE"] = 1.0

    app.config["DECEPTIONS_ENABLED"] = True
    app.config["DECEPTIONS_DYNAMIC_ENABLED"] = True
    app.config["DECEPTIONS_RABBIT_HOLES_ENABLED"] = True
    app.config["DECEPTIONS_FAKE_GOALS_ENABLED"] = True
    app.config["DECEPTIONS_RABBIT_MAX_DEPTH"] = 2
    app.config["DECEPTIONS_RABBIT_MAX_BRANCHING"] = 1
    app.config["DECEPTIONS_FAKE_GOAL_MODE"] = "both"
    app.config["DECEPTIONS_DYNAMIC_FAIL_OPEN"] = True
    app.config["DECEPTIONS_DYNAMIC_ROUTE_STYLE"] = "plausible"

    app.config["DECEPTIONS_ENDPOINT_TRAPS_ENABLED"] = True
    app.config["DECEPTIONS_ENDPOINT_TRAPS_INTERACTIVE"] = True
    app.config["DECEPTIONS_ENDPOINT_TRAPS_MAX_STEPS"] = 2
    app.config["DECEPTIONS_ENDPOINT_TRAPS_FAKE_GOALS_ENABLED"] = True
    app.config["DECEPTIONS_ENDPOINT_TRAPS_RABBIT_HOLES_ENABLED"] = True

    runtime = DeceptionRuntime()
    runtime.init_app(app)
    return runtime