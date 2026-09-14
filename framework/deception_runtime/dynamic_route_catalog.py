"""Plausible dynamic route catalog for rabbit holes and fake goals."""

from __future__ import annotations

import re
from dataclasses import dataclass

from deception_runtime.registry import DeceptionInstance
from deception_runtime.trap_catalog import EndpointTrapClassifier, normalize_endpoint_path


@dataclass(frozen=True)
class DynamicRouteFamily:
    rabbit_hops: tuple[str, ...]
    terminals: tuple[str, ...]
    fake_goals: tuple[str, ...]


_DYNAMIC_ROUTE_FAMILIES: dict[str, DynamicRouteFamily] = {
    "admin_console": DynamicRouteFamily(
        rabbit_hops=(
            "/admin/console/login",
            "/dashboard/internal/overview",
            "/control/panel/tools",
        ),
        terminals=(
            "/admin/console/handoff",
            "/control/panel/review",
        ),
        fake_goals=(
            "/admin/console/export-bundle",
            "/dashboard/internal/checkpoint",
        ),
    ),
    "debug_service": DynamicRouteFamily(
        rabbit_hops=(
            "/debug/service/workers",
            "/internal/status/service/logs",
            "/debug/console/service/config",
        ),
        terminals=(
            "/debug/service/trace-complete",
            "/internal/status/service/terminal",
        ),
        fake_goals=(
            "/debug/service/log-bundle",
            "/internal/status/service/snapshot",
        ),
    ),
    "system_dashboard": DynamicRouteFamily(
        rabbit_hops=(
            "/system/dashboard/overview",
            "/internal/dashboard/panels",
            "/system/dashboard/alerts",
        ),
        terminals=(
            "/system/dashboard/handoff",
            "/internal/dashboard/terminal",
        ),
        fake_goals=(
            "/system/dashboard/snapshot",
            "/internal/dashboard/checkpoint",
        ),
    ),
    "api_backup": DynamicRouteFamily(
        rabbit_hops=(
            "/panel/api_v1/backup/index",
            "/api/internal/export/preview",
            "/data/backup/artifact",
        ),
        terminals=(
            "/panel/api_v1/backup/complete",
            "/api/internal/export/terminal",
        ),
        fake_goals=(
            "/panel/api_v1/backup/manifest",
            "/data/backup/checkpoint",
        ),
    ),
    "hidden_index": DynamicRouteFamily(
        rabbit_hops=(
            "/hidden/index/routes",
            "/private/archive/panel",
            "/legacy/internal/notes",
        ),
        terminals=(
            "/hidden/index/terminal",
            "/legacy/internal/dead-end",
        ),
        fake_goals=(
            "/hidden/index/archive-bundle",
            "/private/archive/checkpoint",
        ),
    ),
    "opaque_internal": DynamicRouteFamily(
        rabbit_hops=(
            "/svc/object/mode",
            "/internal/endpoint/raw",
            "/service/alt/trace",
        ),
        terminals=(
            "/internal/endpoint/terminal",
            "/service/alt/complete",
        ),
        fake_goals=(
            "/internal/endpoint/snapshot",
            "/service/alt/checkpoint",
        ),
    ),
}


class PlausibleDynamicRouteCatalog:
    """Deterministic route builder for plausible dynamic decoy paths."""

    _payload_path_re = re.compile(r"/[a-zA-Z0-9_\-/.~]+")

    def __init__(self):
        self.classifier = EndpointTrapClassifier()

    def _instance_hint_path(self, instance: DeceptionInstance) -> str:
        if instance.honeytoken and instance.honeytoken.get("endpoint_path"):
            return normalize_endpoint_path(str(instance.honeytoken["endpoint_path"]))

        if instance.route and instance.route != "/":
            return normalize_endpoint_path(instance.route)

        if instance.payload_text:
            matches = self._payload_path_re.findall(instance.payload_text)
            for match in matches:
                normalized = normalize_endpoint_path(match)
                if normalized != "/":
                    return normalized

        object_hint = str(instance.raw.get("object") or "").strip().lower()
        intent_hint = str(instance.raw.get("intent") or "").strip().lower()
        if "admin" in object_hint or "admin" in intent_hint:
            return "/admin/console"
        if "endpoint" in object_hint or "exploration" in intent_hint:
            return "/hidden/index"

        return "/hidden"

    def _route_family_for_instance(self, instance: DeceptionInstance) -> DynamicRouteFamily:
        hint_path = self._instance_hint_path(instance)
        classification = self.classifier.classify(hint_path)
        return _DYNAMIC_ROUTE_FAMILIES.get(
            classification.trap_type,
            _DYNAMIC_ROUTE_FAMILIES["hidden_index"],
        )

    def _render_template(self, template: str) -> str:
        return normalize_endpoint_path(template)

    def build_rabbit_routes(
        self,
        *,
        instance: DeceptionInstance,
        challenge_id: str,
        depth: int,
    ) -> tuple[str, list[str], str]:
        family = self._route_family_for_instance(instance)
        hop_paths: list[str] = []
        seen: set[str] = set()

        for hop_index in range(depth):
            template = family.rabbit_hops[hop_index % len(family.rabbit_hops)]
            path = self._render_template(template)
            if path in seen:
                raise ValueError(f"Duplicate canonical rabbit route in family: {path}")
            hop_paths.append(path)
            seen.add(path)

        terminal_template = family.terminals[0]
        terminal_path = self._render_template(terminal_template)
        if terminal_path in seen:
            raise ValueError(f"Duplicate canonical terminal route in family: {terminal_path}")

        return hop_paths[0], hop_paths, terminal_path

    def build_fake_goal_route(self, *, instance: DeceptionInstance, challenge_id: str) -> str:
        family = self._route_family_for_instance(instance)
        return self._render_template(family.fake_goals[0])
