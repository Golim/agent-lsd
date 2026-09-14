"""
Dynamic route registration for rabbit holes and fake goals.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from flask import Blueprint, Response, current_app, g, jsonify, request

from deception_runtime.config import DeceptionConfig
from deception_runtime.dynamic_route_catalog import PlausibleDynamicRouteCatalog
from deception_runtime.fake_goals import FakeGoalManager, FakeGoalPlan
from deception_runtime.logging import StructuredLogger
from deception_runtime.rabbit_holes import RabbitHoleManager, RabbitHoleNode, RabbitHolePlan
from deception_runtime.registry import DeceptionRegistry
from deception_runtime.trap_pages import endpoint_trap_response

logger = StructuredLogger(__name__)


def _event_context(default_challenge_id: str) -> tuple[str, str, str | None]:
    """
    Build request_id, challenge_id, and student_id for telemetry emission.

    Falls back safely when a request context exists but no deception_ctx is set.
    """
    ctx = getattr(g, "deception_ctx", None)
    if ctx:
        return ctx.request_id, ctx.challenge_id, ctx.student_id
    return str(uuid4()), default_challenge_id, None


@dataclass(frozen=True)
class DynamicRouteCandidate:
    """One route registration candidate."""

    path: str
    family: str  # rabbit_hole | fake_goal
    endpoint: str
    view_factory: Callable[[], Callable[[], Response]]


@dataclass(frozen=True)
class DynamicRouteResolution:
    """Dynamic route plans and template variables for one instance."""

    rabbit_plan: RabbitHolePlan | None
    fake_goal_plan: FakeGoalPlan | None

    @property
    def dynamic_decoy_path(self) -> str:
        """Primary path a primitive should advertise."""
        if self.rabbit_plan:
            return self.rabbit_plan.entry_route
        if self.fake_goal_plan:
            return self.fake_goal_plan.endpoint_path
        return ""

    def template_variables(self) -> dict[str, str]:
        """Expose resolved dynamic paths as string template variables."""
        variables: dict[str, str] = {}

        if self.rabbit_plan:
            variables.update(
                {
                    "dynamic_rabbit_entry_route": self.rabbit_plan.entry_route,
                    "dynamic_rabbit_first_hop_route": self.rabbit_plan.nodes[0].path,
                    "dynamic_rabbit_terminal_route": self.rabbit_plan.terminal_path,
                    "dynamic_rabbit_routes": ",".join(self.rabbit_plan.route_paths()),
                }
            )

        if self.fake_goal_plan:
            variables.update(
                {
                    "dynamic_fake_goal_route": self.fake_goal_plan.endpoint_path,
                    "dynamic_fake_goal_terminal_route": f"{self.fake_goal_plan.endpoint_path}?rh_terminal=1",
                }
            )

        if self.dynamic_decoy_path:
            variables["dynamic_decoy_path"] = self.dynamic_decoy_path

        route_values = []
        if self.rabbit_plan:
            route_values.extend(self.rabbit_plan.route_paths())
        if self.fake_goal_plan:
            route_values.append(self.fake_goal_plan.endpoint_path)
        if route_values:
            variables["dynamic_route_list"] = ",".join(dict.fromkeys(route_values))

        return variables


def _instance_with_route_hint(
    instance: DeceptionInstance,
    route_hint_path: str | None,
) -> DeceptionInstance:
    """Return an instance copy whose catalog hint path is explicit."""
    route_hint_path = (route_hint_path or "").strip()
    if not route_hint_path:
        return instance

    raw = dict(instance.raw)
    honeytoken = dict(instance.honeytoken or {})
    honeytoken.setdefault("endpoint_path", route_hint_path)
    raw["honeytoken"] = honeytoken

    return DeceptionInstance(
        instance_id=instance.instance_id,
        primitive_id=instance.primitive_id,
        channel=instance.channel,
        surface=instance.surface,
        payload_text=instance.payload_text,
        placement=instance.placement,
        honeytoken=honeytoken,
        raw=raw,
    )


def resolve_dynamic_routes_for_instance(
    *,
    instance: DeceptionInstance,
    config: DeceptionConfig,
    route_hint_path: str | None = None,
    synthesize_when_missing: bool = True,
) -> DynamicRouteResolution:
    """Build the same dynamic route plans that registration would expose."""
    route_catalog = (
        PlausibleDynamicRouteCatalog()
        if config.dynamic_route_style == "plausible"
        else None
    )
    resolved_instance = _instance_with_route_hint(instance, route_hint_path)

    rabbit_plan = None
    if config.dynamic_enabled and config.dynamic_rabbit_holes_enabled:
        rabbit_plan = RabbitHoleManager(
            route_prefix=config.dynamic_route_prefix,
            max_depth=config.dynamic_rabbit_max_depth,
            max_branching=config.dynamic_rabbit_max_branching,
            default_depth=min(3, config.dynamic_rabbit_max_depth),
            default_branching=min(1, config.dynamic_rabbit_max_branching),
            route_style=config.dynamic_route_style,
            route_catalog=route_catalog,
        ).build_plan(
            instance=resolved_instance,
            challenge_id=config.challenge_id,
            synthesize_when_missing=synthesize_when_missing,
        )

    fake_goal_plan = None
    if config.dynamic_enabled and config.dynamic_fake_goals_enabled:
        fake_goal_plan = FakeGoalManager(
            route_prefix=config.dynamic_route_prefix,
            default_mode=config.dynamic_fake_goal_mode,
            route_style=config.dynamic_route_style,
            route_catalog=route_catalog,
        ).build_plan(
            instance=resolved_instance,
            challenge_id=config.challenge_id,
            synthesize_when_missing=synthesize_when_missing,
        )

    return DynamicRouteResolution(
        rabbit_plan=rabbit_plan,
        fake_goal_plan=fake_goal_plan,
    )


class DynamicRouteManager:
    """Plans and registers dynamic rabbit-hole and fake-goal routes."""

    def __init__(
        self,
        config: DeceptionConfig,
        registry: DeceptionRegistry | None,
    ):
        self.config = config
        self.registry = registry
        self.route_catalog = (
            PlausibleDynamicRouteCatalog()
            if config.dynamic_route_style == "plausible"
            else None
        )
        self.rabbit_manager = RabbitHoleManager(
            route_prefix=config.dynamic_route_prefix,
            max_depth=config.dynamic_rabbit_max_depth,
            max_branching=config.dynamic_rabbit_max_branching,
            default_depth=min(3, config.dynamic_rabbit_max_depth),
            default_branching=min(1, config.dynamic_rabbit_max_branching),
            route_style=config.dynamic_route_style,
            route_catalog=self.route_catalog,
        )
        self.fake_goal_manager = FakeGoalManager(
            route_prefix=config.dynamic_route_prefix,
            default_mode=config.dynamic_fake_goal_mode,
            route_style=config.dynamic_route_style,
            route_catalog=self.route_catalog,
        )

        self.rabbit_plans: dict[str, RabbitHolePlan] = {}
        self.fake_goal_plans: dict[str, FakeGoalPlan] = {}

        self.registered_rabbit_routes: set[str] = set()
        self.registered_fake_goal_routes: set[str] = set()
        self.deduplicated_dynamic_routes = 0
        self.skipped_collisions: list[dict[str, str]] = []

    @property
    def dynamic_enabled(self) -> bool:
        return bool(self.config.dynamic_enabled and self.registry)

    def build_plans(self) -> None:
        """Build deterministic plans for all eligible instances."""
        self.rabbit_plans.clear()
        self.fake_goal_plans.clear()

        if not self.dynamic_enabled or not self.registry:
            return

        for instance_id in self.registry.list_ids():
            instance = self.registry.get(instance_id)
            if not instance:
                continue

            resolution = self.resolve_instance_routes(instance)
            if resolution.rabbit_plan:
                self.rabbit_plans[instance_id] = resolution.rabbit_plan
            if resolution.fake_goal_plan:
                self.fake_goal_plans[instance_id] = resolution.fake_goal_plan

    def resolve_instance_routes(
        self,
        instance: DeceptionInstance,
        *,
        route_hint_path: str | None = None,
        synthesize_when_missing: bool = True,
    ) -> DynamicRouteResolution:
        """Resolve dynamic plans for a single instance."""
        return resolve_dynamic_routes_for_instance(
            instance=instance,
            config=self.config,
            route_hint_path=route_hint_path,
            synthesize_when_missing=synthesize_when_missing,
        )

    def _terminal_next_path(self, plan: RabbitHolePlan) -> str | None:
        if plan.terminal_mode != "fake_goal":
            return None
        fake_plan = self.fake_goal_plans.get(plan.instance_id)
        if not fake_plan:
            return None
        return f"{fake_plan.endpoint_path}?rh_terminal=1"

    def _candidate_endpoint(self, family: str, path: str) -> str:
        suffix = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
        return f"deception_dynamic_{family}_{suffix}"

    def _make_rabbit_hop_handler(self, plan: RabbitHolePlan, node: RabbitHoleNode) -> Callable[[], Response]:
        def _handle() -> Response:
            runtime = current_app.extensions.get("deception_runtime")
            telemetry = getattr(runtime, "telemetry", None)
            request_id, challenge_id, student_id = _event_context(plan.challenge_id)

            if telemetry:
                common = {
                    "request_id": request_id,
                    "challenge_id": challenge_id,
                    "route": request.path,
                    "method": request.method,
                    "instance_id": plan.instance_id,
                    "student_id": student_id,
                    "user_agent": request.headers.get("User-Agent"),
                    "remote_addr": request.remote_addr,
                }
                extra = {
                    "hop_index": node.hop_index,
                    "total_depth": plan.depth,
                    "next_path": node.next_path,
                    "topology": plan.topology,
                }
                if node.hop_index == 0:
                    telemetry.emit(event_type="rabbit_hole_entered", extra=extra, **common)
                telemetry.emit(event_type="rabbit_hole_hop", extra=extra, **common)

            if (
                runtime
                and getattr(runtime, "endpoint_trap_classifier", None)
                and self.config.endpoint_traps_enabled
                and self.config.endpoint_traps_rabbit_holes_enabled
            ):
                classification = runtime.endpoint_trap_classifier.classify(request.path)
                return endpoint_trap_response(
                    runtime=runtime,
                    classification=classification,
                    instance_id=plan.instance_id,
                    endpoint_path=request.path,
                    interactive=self.config.endpoint_traps_interactive,
                    max_steps=self.config.endpoint_traps_max_steps,
                    fake_goal_enabled=False,
                    related_endpoint_path=node.next_path,
                )

            html = self.rabbit_manager.render_hop_page(plan=plan, node=node)
            return Response(html, status=200, mimetype="text/html")

        _handle.__name__ = self._candidate_endpoint("rabbit_hop", node.path)
        return _handle

    def _make_rabbit_terminal_handler(self, plan: RabbitHolePlan) -> Callable[[], Response]:
        def _handle() -> Response:
            runtime = current_app.extensions.get("deception_runtime")
            telemetry = getattr(runtime, "telemetry", None)
            request_id, challenge_id, student_id = _event_context(plan.challenge_id)
            next_path = self._terminal_next_path(plan)

            if telemetry:
                telemetry.emit(
                    event_type="rabbit_hole_terminal",
                    request_id=request_id,
                    challenge_id=challenge_id,
                    route=request.path,
                    method=request.method,
                    instance_id=plan.instance_id,
                    student_id=student_id,
                    user_agent=request.headers.get("User-Agent"),
                    remote_addr=request.remote_addr,
                    extra={
                        "hop_index": plan.depth,
                        "total_depth": plan.depth,
                        "next_path": next_path,
                        "topology": plan.topology,
                    },
                )

            html = self.rabbit_manager.render_terminal_page(plan=plan, next_path=next_path)
            return Response(html, status=200, mimetype="text/html")

        _handle.__name__ = self._candidate_endpoint("rabbit_terminal", plan.terminal_path)
        return _handle

    def _make_fake_goal_handler(self, plan: FakeGoalPlan) -> Callable[[], Response]:
        def _handle() -> Response:
            runtime = current_app.extensions.get("deception_runtime")
            telemetry = getattr(runtime, "telemetry", None)
            request_id, challenge_id, student_id = _event_context(plan.challenge_id)
            rabbit_hole_terminal = request.args.get("rh_terminal", "").lower() in {"1", "true", "yes"}
            fake_flag_hash = self.fake_goal_manager.fake_flag_hash(plan.fake_flag)

            if telemetry:
                base_extra = {
                    "endpoint_path": plan.endpoint_path,
                    "fake_goal_mode": plan.mode,
                    "fake_flag_hash": fake_flag_hash,
                    "rabbit_hole_terminal": rabbit_hole_terminal,
                }
                common = {
                    "request_id": request_id,
                    "challenge_id": challenge_id,
                    "route": request.path,
                    "method": request.method,
                    "instance_id": plan.instance_id,
                    "student_id": student_id,
                    "user_agent": request.headers.get("User-Agent"),
                    "remote_addr": request.remote_addr,
                }
                telemetry.emit(event_type="fake_goal_viewed", extra=base_extra, **common)
                if self.fake_goal_manager.mode_has_flag(plan.mode):
                    telemetry.emit(event_type="fake_goal_flag_shown", extra=base_extra, **common)
                if self.fake_goal_manager.mode_has_success(plan.mode):
                    telemetry.emit(event_type="fake_goal_success_shown", extra=base_extra, **common)

            html = self.fake_goal_manager.render_page(
                plan=plan,
                rabbit_hole_terminal=rabbit_hole_terminal,
            )
            return Response(html, status=200, mimetype="text/html")

        _handle.__name__ = self._candidate_endpoint("fake_goal", plan.endpoint_path)
        return _handle

    def _build_candidates(self) -> list[DynamicRouteCandidate]:
        candidates: list[DynamicRouteCandidate] = []

        for plan in self.rabbit_plans.values():
            for node in plan.nodes:
                candidates.append(
                    DynamicRouteCandidate(
                        path=node.path,
                        family="rabbit_hole",
                        endpoint=self._candidate_endpoint("rabbit_hop", node.path),
                        view_factory=lambda p=plan, n=node: self._make_rabbit_hop_handler(p, n),
                    )
                )

            if plan.entry_route != plan.nodes[0].path:
                first_node = plan.nodes[0]
                candidates.append(
                    DynamicRouteCandidate(
                        path=plan.entry_route,
                        family="rabbit_hole",
                        endpoint=self._candidate_endpoint("rabbit_entry", plan.entry_route),
                        view_factory=lambda p=plan, n=first_node: self._make_rabbit_hop_handler(p, n),
                    )
                )

            candidates.append(
                DynamicRouteCandidate(
                    path=plan.terminal_path,
                    family="rabbit_hole",
                    endpoint=self._candidate_endpoint("rabbit_terminal", plan.terminal_path),
                    view_factory=lambda p=plan: self._make_rabbit_terminal_handler(p),
                )
            )

        for plan in self.fake_goal_plans.values():
            candidates.append(
                DynamicRouteCandidate(
                    path=plan.endpoint_path,
                    family="fake_goal",
                    endpoint=self._candidate_endpoint("fake_goal", plan.endpoint_path),
                    view_factory=lambda p=plan: self._make_fake_goal_handler(p),
                )
            )

        return candidates

    def _record_collision(self, path: str, reason: str) -> None:
        self.skipped_collisions.append({"path": path, "reason": reason})
        logger.warning("Skipping dynamic route due to collision", path=path, reason=reason)

    def _handle_collision(self, path: str, reason: str) -> None:
        self._record_collision(path, reason)
        if not self.config.dynamic_fail_open:
            raise RuntimeError(f"Dynamic route collision at {path}: {reason}")

    def _to_blueprint_rule(self, path: str) -> str:
        prefix = self.config.dynamic_route_prefix
        if path == prefix:
            return "/"
        if path.startswith(f"{prefix}/"):
            return path[len(prefix):]
        # Keep fail-open behavior for malformed paths.
        return path

    def _register_debug_endpoint(self, app) -> None:
        endpoint = "deception_dynamic_stats"
        if endpoint in app.view_functions:
            return

        app.add_url_rule(
            "/__deception__/dynamic_stats",
            endpoint=endpoint,
            view_func=lambda: jsonify(self.stats()),
            methods=["GET"],
        )

    def register(self, app) -> None:
        """Build and register dynamic routes for enabled families."""
        if not self.dynamic_enabled:
            logger.info("Dynamic deception routes disabled")
            return

        self.build_plans()
        self.registered_rabbit_routes.clear()
        self.registered_fake_goal_routes.clear()
        self.deduplicated_dynamic_routes = 0
        self.skipped_collisions.clear()

        candidates = self._build_candidates()
        if not candidates:
            self._register_debug_endpoint(app)
            logger.info("No dynamic routes eligible for registration")
            return

        existing_paths = {rule.rule for rule in app.url_map.iter_rules()}
        planned_paths = set(existing_paths)
        dynamic_path_families: dict[str, str] = {}

        blueprint = None
        if self.config.dynamic_register_blueprint and self.config.dynamic_route_style == "namespaced":
            blueprint = Blueprint(
                "deception_dynamic",
                __name__,
                url_prefix=self.config.dynamic_route_prefix,
            )

        for candidate in candidates:
            existing_family = dynamic_path_families.get(candidate.path)
            if existing_family:
                if existing_family != candidate.family:
                    self._handle_collision(candidate.path, "dynamic route family conflict")
                else:
                    self.deduplicated_dynamic_routes += 1
                continue

            if candidate.path in planned_paths:
                self._handle_collision(candidate.path, "route already exists")
                continue

            view_func = candidate.view_factory()
            try:
                if blueprint:
                    rule = self._to_blueprint_rule(candidate.path)
                    blueprint.add_url_rule(
                        rule=rule,
                        endpoint=candidate.endpoint,
                        view_func=view_func,
                        methods=["GET"],
                    )
                else:
                    app.add_url_rule(
                        rule=candidate.path,
                        endpoint=candidate.endpoint,
                        view_func=view_func,
                        methods=["GET"],
                    )
            except Exception as exc:
                self._handle_collision(candidate.path, f"registration_error:{exc}")
                continue

            planned_paths.add(candidate.path)
            dynamic_path_families[candidate.path] = candidate.family
            if candidate.family == "rabbit_hole":
                self.registered_rabbit_routes.add(candidate.path)
            else:
                self.registered_fake_goal_routes.add(candidate.path)

        if blueprint:
            app.register_blueprint(blueprint)
            logger.info(
                "Registered dynamic blueprint",
                url_prefix=self.config.dynamic_route_prefix,
                rabbit_routes=len(self.registered_rabbit_routes),
                fake_goal_routes=len(self.registered_fake_goal_routes),
            )
        else:
            logger.info(
                "Registered dynamic routes directly on app",
                rabbit_routes=len(self.registered_rabbit_routes),
                fake_goal_routes=len(self.registered_fake_goal_routes),
            )

        self._register_debug_endpoint(app)

    def stats(self) -> dict[str, Any]:
        """Return dynamic route manager stats for health/debug endpoints."""
        return {
            "enabled": {
                "dynamic": bool(self.config.dynamic_enabled),
                "rabbit_holes": bool(self.config.dynamic_rabbit_holes_enabled),
                "fake_goals": bool(self.config.dynamic_fake_goals_enabled),
            },
            "route_prefix": self.config.dynamic_route_prefix,
            "route_style": self.config.dynamic_route_style,
            "rabbit_hole_routes": len(self.registered_rabbit_routes),
            "fake_goal_routes": len(self.registered_fake_goal_routes),
            "deduplicated_dynamic_routes": self.deduplicated_dynamic_routes,
            "skipped_collisions": len(self.skipped_collisions),
            "collisions": list(self.skipped_collisions),
            "rabbit_hole_instances": len(self.rabbit_plans),
            "fake_goal_instances": len(self.fake_goal_plans),
            "rabbit_hole_route_samples": sorted(self.registered_rabbit_routes)[:20],
            "fake_goal_route_samples": sorted(self.registered_fake_goal_routes)[:20],
        }
