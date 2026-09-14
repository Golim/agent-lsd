"""
Flask extension for deception runtime.
"""

from flask import Blueprint, Flask, abort, g, jsonify, request

from deception_runtime import __version__
from deception_runtime.blueprints import create_honeytoken_handler, create_telemetry_stats_blueprint
from deception_runtime.config import DeceptionConfig
from deception_runtime.context import DeceptionContext
from deception_runtime.dynamic_routes import DynamicRouteManager
from deception_runtime.honeytokens import HoneytokenMatcher
from deception_runtime.logging import StructuredLogger
from deception_runtime.registry import DeceptionRegistry
from deception_runtime.sinks import NoOpSink, create_sink
from deception_runtime.telemetry import TelemetryCoordinator
from deception_runtime.trap_catalog import EndpointTrapClassifier

logger = StructuredLogger(__name__)


class DeceptionRuntime:
    """
    Flask extension that enables deception injection with minimal code changes.

    Usage:
        from deception_runtime import DeceptionRuntime

        app = Flask(__name__)
        rt = DeceptionRuntime()
        rt.init_app(app)
    """

    def __init__(self, app: Flask | None = None):
        """
        Initialize the extension.

        Args:
            app: Optional Flask app to initialize immediately
        """
        self.config: DeceptionConfig | None = None
        self.registry: DeceptionRegistry | None = None
        self.telemetry: TelemetryCoordinator | None = None
        self.honeytoken_matcher: HoneytokenMatcher | None = None
        self.dynamic_route_manager: DynamicRouteManager | None = None
        self.endpoint_trap_classifier: EndpointTrapClassifier | None = None

        if app:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """
        Initialize the extension with a Flask app.

        Args:
            app: Flask application instance
        """
        # Load configuration
        self.config = DeceptionConfig.from_flask_config(app.config, app.name)

        logger.info(
            "Initializing DeceptionRuntime",
            enabled=self.config.enabled,
            challenge_id=self.config.challenge_id,
            instances_dir=self.config.instances_dir,
        )

        # Load registry if enabled
        if self.config.enabled:
            try:
                self.registry = DeceptionRegistry(
                    instances_dir=self.config.instances_dir,
                    schema_path=self.config.schema_path,
                    validate_schema=True,
                )
                logger.info(
                    "Registry loaded",
                    instance_count=len(self.registry),
                )
            except Exception as e:
                logger.exception(
                    "Failed to load registry",
                    error=str(e),
                )
                # Fail loudly - do not continue with broken registry
                raise RuntimeError(f"Failed to load deception registry: {e}") from e
        else:
            logger.info("Deceptions disabled, skipping registry load")
            self.registry = None

        # Initialize telemetry
        self._init_telemetry()

        # Initialize endpoint trap classifier
        self._init_endpoint_traps()

        # Initialize honeytokens
        self._init_honeytokens(app)

        # Initialize dynamic deception routes
        self._init_dynamic_routes(app)

        # Register extension
        app.extensions["deception_runtime"] = self

        # Register Flask hooks
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.teardown_request(self._teardown_request)

        # Register health blueprint
        self._register_health_blueprint(app)

        # Register telemetry stats blueprint
        if self.config.telemetry_enabled:
            app.register_blueprint(create_telemetry_stats_blueprint())

    def _init_telemetry(self) -> None:
        """Initialize telemetry coordinator and sink."""
        if not self.config.telemetry_enabled:
            logger.info("Telemetry disabled")
            self.telemetry = TelemetryCoordinator(
                sink=NoOpSink(),
                sample_rate=0.0,
                validate_events=False,
            )
            return

        try:
            # Create sink
            sink = create_sink(
                sink_type=self.config.telemetry_sink,
                path=self.config.telemetry_path,
                fsync=self.config.telemetry_fsync,
            )

            # Create coordinator
            self.telemetry = TelemetryCoordinator(
                sink=sink,
                sample_rate=self.config.telemetry_sample_rate,
                validate_events=True,
            )

            logger.info(
                "Telemetry initialized",
                sink=self.config.telemetry_sink,
                path=self.config.telemetry_path,
                sample_rate=self.config.telemetry_sample_rate,
            )
        except Exception as e:
            logger.error("Failed to initialize telemetry", error=str(e))
            # Fall back to no-op sink
            self.telemetry = TelemetryCoordinator(
                sink=NoOpSink(),
                sample_rate=0.0,
                validate_events=False,
            )

    def _init_honeytokens(self, app: Flask) -> None:
        """
        Initialize honeytoken matcher and register URL endpoints.

        Args:
            app: Flask application
        """
        if not self.config.honeytokens_enabled or not self.registry:
            logger.info("Honeytokens disabled")
            self.honeytoken_matcher = None
            return

        try:
            # Create honeytoken matcher
            self.honeytoken_matcher = HoneytokenMatcher(
                registry=self.registry,
                protected_routes=self.config.protected_routes,
                honeytoken_param=self.config.honeytoken_param,
                honeytoken_header=self.config.honeytoken_header,
                honeytoken_cookie=self.config.honeytoken_cookie,
                value_prefix=self.config.honeytoken_value_prefix,
            )

            # Register URL endpoints for honeytokens
            registered_count = 0
            collision_count = 0

            for path in self.honeytoken_matcher.get_url_paths():
                # Check if path is protected
                if self.honeytoken_matcher.is_path_protected(path):
                    logger.warning(
                        "Honeytoken path is protected, skipping endpoint registration",
                        path=path,
                    )
                    collision_count += 1
                    continue

                # Check for existing route
                endpoint_name = f"honeytoken_{abs(hash(path))}"

                # Try to register
                try:
                    instance_ids = self.honeytoken_matcher.match_url(path)
                    if not instance_ids:
                        continue

                    # Use first instance for this path
                    instance_id = instance_ids[0]

                    handler = create_honeytoken_handler(
                        instance_id=instance_id,
                        path=path,
                        response_mode=self.config.honeytoken_response_mode,
                    )

                    app.add_url_rule(
                        path,
                        endpoint=endpoint_name,
                        view_func=handler,
                        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
                    )

                    registered_count += 1

                except Exception as e:
                    # Likely a collision with existing route
                    logger.warning(
                        "Failed to register honeytoken endpoint (collision?)",
                        path=path,
                        error=str(e),
                    )
                    collision_count += 1

            logger.info(
                "Honeytokens initialized",
                registered=registered_count,
                collisions=collision_count,
                passive_detection_enabled=True,
            )

        except Exception as e:
            logger.error("Failed to initialize honeytokens", error=str(e))
            self.honeytoken_matcher = None

    def _init_endpoint_traps(self) -> None:
        """Initialize endpoint trap classifier when feature is enabled."""
        if not self.config.endpoint_traps_enabled:
            self.endpoint_trap_classifier = None
            logger.info("Endpoint traps disabled")
            return

        try:
            self.endpoint_trap_classifier = EndpointTrapClassifier(
                map_file_path=self.config.endpoint_trap_map_file or None,
                opaque_patterns=self.config.endpoint_traps_opaque_patterns,
            )
            logger.info(
                "Endpoint traps initialized",
                interactive=self.config.endpoint_traps_interactive,
                max_steps=self.config.endpoint_traps_max_steps,
                map_file=bool(self.config.endpoint_trap_map_file),
                rabbit_holes=self.config.endpoint_traps_rabbit_holes_enabled,
            )
        except Exception as e:
            logger.error("Failed to initialize endpoint trap classifier", error=str(e))
            self.endpoint_trap_classifier = None

    def _init_dynamic_routes(self, app: Flask) -> None:
        """
        Initialize and register dynamic rabbit-hole/fake-goal routes.

        Args:
            app: Flask application
        """
        if not self.registry or not self.config.dynamic_enabled:
            logger.info("Dynamic deception routes disabled")
            self.dynamic_route_manager = None
            return

        if not self.config.dynamic_rabbit_holes_enabled and not self.config.dynamic_fake_goals_enabled:
            logger.info("Dynamic deception families disabled")
            self.dynamic_route_manager = None
            return

        try:
            self.dynamic_route_manager = DynamicRouteManager(
                config=self.config,
                registry=self.registry,
            )
            self.dynamic_route_manager.register(app)
            logger.info(
                "Dynamic routes initialized",
                rabbit_holes=self.config.dynamic_rabbit_holes_enabled,
                fake_goals=self.config.dynamic_fake_goals_enabled,
                prefix=self.config.dynamic_route_prefix,
            )
        except Exception as e:
            logger.error("Failed to initialize dynamic routes", error=str(e))
            if self.config.dynamic_fail_open:
                self.dynamic_route_manager = None
                logger.warning("Dynamic route init failed open; continuing without dynamic routes")
            else:
                raise RuntimeError(f"Failed to initialize dynamic routes: {e}") from e

    def _before_request(self) -> None:
        """
        Flask before_request hook to populate g.deception_ctx and emit telemetry.
        """
        if not self.config:
            # Extension not initialized
            g.deception_ctx = DeceptionContext.create_disabled("unknown")
            return

        # Check if deceptions are enabled
        if not self.config.enabled or not self.registry:
            g.deception_ctx = DeceptionContext.create_disabled(self.config.challenge_id)
        else:
            # Extract instance_id from header or query parameter
            instance_id = request.headers.get(self.config.instance_header)
            if not instance_id:
                instance_id = request.args.get(self.config.instance_query)

            # Extract student_id from header or cookie
            student_id = request.headers.get(self.config.student_header)
            if not student_id:
                student_id = request.cookies.get(self.config.student_cookie)

            # If no instance_id provided, create disabled context
            if not instance_id:
                g.deception_ctx = DeceptionContext.create_disabled(self.config.challenge_id)
                logger.debug("No instance_id provided, deceptions disabled for request")
            else:
                # Check if instance exists in registry
                instance = self.registry.get(instance_id)

                if not instance and self.config.fail_closed:
                    # Fail closed: abort with 400 if instance not found
                    logger.warning(
                        "Instance not found (fail_closed=true)",
                        instance_id=instance_id,
                        student_id=student_id,
                    )
                    abort(
                        400,
                        description=f"Invalid deception instance: {instance_id}",
                    )

                if not instance:
                    # Fail open: log warning but continue
                    logger.warning(
                        "Instance not found (fail_open)",
                        instance_id=instance_id,
                        student_id=student_id,
                    )
                    g.deception_ctx = DeceptionContext.create_disabled(self.config.challenge_id)
                else:
                    # Create enabled context
                    g.deception_ctx = DeceptionContext.create_enabled(
                        challenge_id=self.config.challenge_id,
                        instance_id=instance_id,
                        student_id=student_id,
                    )

                    logger.debug(
                        "Deception context activated",
                        instance_id=instance_id,
                        student_id=student_id,
                        request_id=g.deception_ctx.request_id,
                        channel=instance.channel,
                        surface=instance.surface,
                    )

        # Emit request_start telemetry event
        if self.telemetry and self.config.telemetry_enabled:
            ctx = g.deception_ctx
            self.telemetry.emit(
                event_type="request_start",
                request_id=ctx.request_id,
                challenge_id=ctx.challenge_id,
                route=request.path,
                method=request.method,
                instance_id=ctx.instance_id,
                student_id=ctx.student_id,
                user_agent=request.headers.get("User-Agent"),
                remote_addr=request.remote_addr,
            )

            # Emit instance_selected event if instance is active
            if ctx.instance_id:
                self.telemetry.emit(
                    event_type="instance_selected",
                    request_id=ctx.request_id,
                    challenge_id=ctx.challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=ctx.instance_id,
                    student_id=ctx.student_id,
                    user_agent=request.headers.get("User-Agent"),
                    remote_addr=request.remote_addr,
                )

        # Check for honeytoken hits (passive detection)
        if self.honeytoken_matcher and self.config.honeytokens_enabled:
            self._check_honeytokens()

    def _check_honeytokens(self) -> None:
        """Check for honeytoken hits in current request."""
        ctx = g.deception_ctx

        # Check URL path match
        matched_instances = self.honeytoken_matcher.match_url(request.path)
        for instance_id in matched_instances:
            self.telemetry.emit(
                event_type="honeytoken_hit",
                request_id=ctx.request_id,
                challenge_id=ctx.challenge_id,
                route=request.path,
                method=request.method,
                instance_id=instance_id,
                student_id=ctx.student_id,
                user_agent=request.headers.get("User-Agent"),
                remote_addr=request.remote_addr,
                extra={
                    "token_type": "url",
                    "matched_path": request.path,
                    "detected_via": "passive",
                },
            )
            logger.info(
                "Honeytoken hit (passive URL)",
                instance_id=instance_id,
                path=request.path,
            )

        # Check param honeytoken
        param_value = request.args.get(self.config.honeytoken_param)
        if param_value:
            matched_instances = self.honeytoken_matcher.match_param(param_value)
            for instance_id in matched_instances:
                self.telemetry.emit(
                    event_type="honeytoken_hit",
                    request_id=ctx.request_id,
                    challenge_id=ctx.challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=instance_id,
                    student_id=ctx.student_id,
                    user_agent=request.headers.get("User-Agent"),
                    remote_addr=request.remote_addr,
                    extra={
                        "token_type": "param",
                        "param_name": self.config.honeytoken_param,
                        "param_value": param_value,
                        "detected_via": "passive",
                    },
                )
                logger.info(
                    "Honeytoken hit (param)",
                    instance_id=instance_id,
                    param=self.config.honeytoken_param,
                )

        # Check header honeytoken
        header_value = request.headers.get(self.config.honeytoken_header)
        if header_value:
            matched_instances = self.honeytoken_matcher.match_header(header_value)
            for instance_id in matched_instances:
                self.telemetry.emit(
                    event_type="honeytoken_hit",
                    request_id=ctx.request_id,
                    challenge_id=ctx.challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=instance_id,
                    student_id=ctx.student_id,
                    user_agent=request.headers.get("User-Agent"),
                    remote_addr=request.remote_addr,
                    extra={
                        "token_type": "header",
                        "header_name": self.config.honeytoken_header,
                        "header_value": header_value,
                        "detected_via": "passive",
                    },
                )
                logger.info(
                    "Honeytoken hit (header)",
                    instance_id=instance_id,
                    header=self.config.honeytoken_header,
                )

        # Check cookie honeytoken
        cookie_value = request.cookies.get(self.config.honeytoken_cookie)
        if cookie_value:
            matched_instances = self.honeytoken_matcher.match_cookie(cookie_value)
            for instance_id in matched_instances:
                self.telemetry.emit(
                    event_type="honeytoken_hit",
                    request_id=ctx.request_id,
                    challenge_id=ctx.challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=instance_id,
                    student_id=ctx.student_id,
                    user_agent=request.headers.get("User-Agent"),
                    remote_addr=request.remote_addr,
                    extra={
                        "token_type": "cookie",
                        "cookie_name": self.config.honeytoken_cookie,
                        "cookie_value": cookie_value,
                        "detected_via": "passive",
                    },
                )
                logger.info(
                    "Honeytoken hit (cookie)",
                    instance_id=instance_id,
                    cookie=self.config.honeytoken_cookie,
                )

    def _after_request(self, response):
        """
        Flask after_request hook to apply deceptions and emit request_end telemetry.

        Args:
            response: Flask response object

        Returns:
            Response object (potentially modified with deceptions)
        """
        # Apply deceptions to response if enabled
        if self.config.enabled and self.config.apply_enabled:
            from deception_runtime.apply import apply_deceptions_to_response

            config_dict = {
                "enabled": self.config.enabled,
                "apply_enabled": self.config.apply_enabled,
                "fail_open": self.config.apply_fail_open,
                "max_bytes": self.config.apply_max_bytes,
                "allowed_routes": self.config.apply_allowed_routes,
                "allowed_methods": self.config.apply_allowed_methods,
            }

            response = apply_deceptions_to_response(response, self, config_dict)

        # Emit telemetry
        if self.telemetry and self.config.telemetry_enabled:
            ctx = getattr(g, "deception_ctx", None)
            if ctx:
                self.telemetry.emit(
                    event_type="request_end",
                    request_id=ctx.request_id,
                    challenge_id=ctx.challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=ctx.instance_id,
                    student_id=ctx.student_id,
                    status_code=response.status_code,
                    user_agent=request.headers.get("User-Agent"),
                    remote_addr=request.remote_addr,
                )

        return response

    def _teardown_request(self, exc=None):
        """
        Flask teardown_request hook to ensure request_end is emitted on errors.

        Args:
            exc: Exception if request failed
        """
        # Only emit if after_request didn't run (e.g., exception)
        if exc and self.telemetry and self.config.telemetry_enabled:
            ctx = getattr(g, "deception_ctx", None)
            if ctx:
                # Check if we already emitted request_end
                # (This is a simple heuristic - in production might want a flag)
                self.telemetry.emit(
                    event_type="request_end",
                    request_id=ctx.request_id,
                    challenge_id=ctx.challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=ctx.instance_id,
                    student_id=ctx.student_id,
                    status_code=500,  # Assume error
                    user_agent=request.headers.get("User-Agent"),
                    remote_addr=request.remote_addr,
                    extra={"exception": str(exc) if exc else None},
                )

    def _register_health_blueprint(self, app: Flask) -> None:
        """
        Register health check blueprint.

        Args:
            app: Flask application
        """
        bp = Blueprint("deception_health", __name__, url_prefix="/__deception__")

        @bp.route("/health", methods=["GET"])
        def health():
            """Health check endpoint."""
            if not self.config:
                return jsonify({
                    "status": "error",
                    "message": "Extension not initialized",
                }), 500

            return jsonify({
                "status": "ok",
                "version": __version__,
                "enabled": self.config.enabled,
                "challenge_id": self.config.challenge_id,
                "registry_size": len(self.registry) if self.registry else 0,
                "config": {
                    "instances_dir": self.config.instances_dir,
                    "fail_closed": self.config.fail_closed,
                    "instance_header": self.config.instance_header,
                    "instance_query": self.config.instance_query,
                },
            })

        app.register_blueprint(bp)
        logger.info("Registered health blueprint", url_prefix="/__deception__")
