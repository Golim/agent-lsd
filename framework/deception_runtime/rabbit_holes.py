"""
Deterministic rabbit-hole plan generation and rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flask import render_template_string

from deception_runtime.logging import StructuredLogger
from deception_runtime.registry import DeceptionInstance

if TYPE_CHECKING:
    from deception_runtime.dynamic_route_catalog import PlausibleDynamicRouteCatalog

logger = StructuredLogger(__name__)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Best-effort int parsing with min/max clamp."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _endpoint_hint(path: str | None) -> dict[str, str | None]:
    """Build realistic internal copy for a linked workflow endpoint."""
    if not path:
        return {
            "label": None,
            "message": "No linked workflow artifact is currently pending review.",
            "link_text": None,
        }

    normalized = path.strip() or "/"
    path_text = normalized.lower()
    if "export" in path_text or "bundle" in path_text:
        return {
            "label": "Export Notice",
            "message": f"The export manifest references {normalized} for bundle verification.",
            "link_text": "Review export manifest",
        }
    if "handoff" in path_text:
        return {
            "label": "Handoff Note",
            "message": f"Operations marked {normalized} as the handoff record for this workflow.",
            "link_text": "Open handoff record",
        }
    if "checkpoint" in path_text:
        return {
            "label": "Checkpoint Note",
            "message": f"Checkpoint metadata is archived under {normalized}.",
            "link_text": "Review checkpoint metadata",
        }
    if "terminal" in path_text or "final" in path_text or "complete" in path_text:
        return {
            "label": "Review Note",
            "message": f"The final review artifact is listed at {normalized}.",
            "link_text": "Open review artifact",
        }
    if "logs" in path_text or "trace" in path_text:
        return {
            "label": "Trace Note",
            "message": f"Worker trace output points to {normalized} for log correlation.",
            "link_text": "Inspect trace output",
        }
    if "config" in path_text:
        return {
            "label": "Configuration Note",
            "message": f"The service configuration index references {normalized}.",
            "link_text": "Inspect configuration index",
        }
    if "archive" in path_text or "legacy" in path_text:
        return {
            "label": "Archive Note",
            "message": f"Legacy route metadata lists {normalized} as the related archive record.",
            "link_text": "Open archive record",
        }
    if "dashboard" in path_text or "overview" in path_text or "panel" in path_text:
        return {
            "label": "Dashboard Note",
            "message": f"Dashboard metadata links this item with {normalized}.",
            "link_text": "Open dashboard reference",
        }
    if "login" in path_text or "admin" in path_text or "control" in path_text:
        return {
            "label": "Access Note",
            "message": f"Access-control notes reference {normalized} for operator review.",
            "link_text": "Open access record",
        }

    return {
        "label": "Reference Note",
        "message": f"Related endpoint metadata is available at {normalized}.",
        "link_text": "Open endpoint reference",
    }


@dataclass(frozen=True)
class RabbitHoleNode:
    """One hop inside a rabbit-hole graph."""

    path: str
    hop_index: int
    next_path: str
    total_depth: int
    topology: str = "linear"


@dataclass(frozen=True)
class RabbitHolePlan:
    """Deterministic rabbit-hole route plan for one instance."""

    instance_id: str
    challenge_id: str
    enabled: bool
    topology: str
    depth: int
    branching: int
    entry_route: str
    terminal_path: str
    terminal_mode: str
    nodes: tuple[RabbitHoleNode, ...]

    def route_paths(self) -> list[str]:
        """All unique route paths represented by this plan."""
        paths = {self.entry_route, self.terminal_path}
        paths.update(node.path for node in self.nodes)
        return sorted(paths)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe plan structure."""
        return {
            "instance_id": self.instance_id,
            "challenge_id": self.challenge_id,
            "enabled": self.enabled,
            "topology": self.topology,
            "depth": self.depth,
            "branching": self.branching,
            "entry_route": self.entry_route,
            "terminal_path": self.terminal_path,
            "terminal_mode": self.terminal_mode,
            "routes": self.route_paths(),
        }


class RabbitHoleManager:
    """Build and render rabbit-hole plans with deterministic routes."""

    def __init__(
        self,
        route_prefix: str = "/_deception",
        max_depth: int = 3,
        max_branching: int = 1,
        default_depth: int = 3,
        default_branching: int = 1,
        route_style: str = "namespaced",
        route_catalog: "PlausibleDynamicRouteCatalog | None" = None,
    ):
        self.route_prefix = route_prefix
        self.max_depth = max(1, max_depth)
        self.max_branching = max(1, max_branching)
        self.default_depth = max(1, min(default_depth, self.max_depth))
        self.default_branching = max(1, min(default_branching, self.max_branching))
        self.route_style = route_style if route_style in {"namespaced", "plausible"} else "namespaced"
        self.route_catalog = route_catalog
        self._template = self._load_template()

    def _load_template(self) -> str:
        template_path = Path(__file__).parent / "templates" / "workflow_stage.html"
        if not template_path.exists():
            # Safe fallback in case template packaging is incomplete.
            return (
                "<!doctype html><html><head><title>Workspace</title></head><body>"
                "<h1>Workspace</h1><p>{{ route_hint.message }}</p>"
                "{% if next_path %}<p><a href='{{ next_path }}'>{{ route_hint.link_text }}</a></p>{% endif %}"
                "</body></html>"
            )
        return template_path.read_text(encoding="utf-8")

    def build_plan(
        self,
        instance: DeceptionInstance,
        challenge_id: str,
        synthesize_when_missing: bool = False,
    ) -> RabbitHolePlan | None:
        """Build rabbit-hole plan for an instance, or None if disabled."""
        dynamic_cfg = instance.raw.get("dynamic", {})
        if not isinstance(dynamic_cfg, dict):
            dynamic_cfg = {}

        instance_dynamic_enabled = dynamic_cfg.get("enabled")
        if instance_dynamic_enabled is False:
            return None

        rabbit_cfg = dynamic_cfg.get("rabbit_hole", {})
        if not isinstance(rabbit_cfg, dict):
            rabbit_cfg = {}

        rabbit_enabled = rabbit_cfg.get("enabled")
        if rabbit_enabled is None:
            rabbit_enabled = synthesize_when_missing
        if not bool(rabbit_enabled):
            return None

        depth = _clamp_int(
            rabbit_cfg.get("depth"),
            default=self.default_depth,
            minimum=1,
            maximum=self.max_depth,
        )
        branching = _clamp_int(
            rabbit_cfg.get("branching"),
            default=self.default_branching,
            minimum=1,
            maximum=self.max_branching,
        )

        style = str(rabbit_cfg.get("style", "linear")).strip().lower()
        topology = "branching_tree" if style == "branching" and branching > 1 else "linear"

        terminal_mode = str(rabbit_cfg.get("terminal_mode", "dead_end")).strip().lower()
        if terminal_mode not in {"dead_end", "fake_goal"}:
            terminal_mode = "dead_end"

        if self.route_style == "plausible" and self.route_catalog:
            entry_route, hop_paths, terminal_path = self.route_catalog.build_rabbit_routes(
                instance=instance,
                challenge_id=challenge_id,
                depth=depth,
            )
        else:
            base_path = f"{self.route_prefix}/rabbit"
            hop_paths = [f"{base_path}/hop/{hop}" for hop in range(depth)]
            terminal_path = f"{base_path}/final"
            entry_route = hop_paths[0]

        configured_entry = str(rabbit_cfg.get("entry_route") or "").strip()
        if configured_entry:
            if not configured_entry.startswith("/"):
                logger.warning(
                    "Rabbit-hole entry route must be an absolute path; using deterministic default",
                    instance_id=instance.instance_id,
                    entry_route=configured_entry,
                )
            elif self.route_style == "namespaced" and not configured_entry.startswith(f"{self.route_prefix}/"):
                logger.warning(
                    "Rabbit-hole entry route must stay namespaced; using deterministic default",
                    instance_id=instance.instance_id,
                    entry_route=configured_entry,
                    route_prefix=self.route_prefix,
                )
            else:
                entry_route = configured_entry

        nodes = []
        for hop_index, path in enumerate(hop_paths):
            next_path = terminal_path if hop_index == (depth - 1) else hop_paths[hop_index + 1]
            nodes.append(
                RabbitHoleNode(
                    path=path,
                    hop_index=hop_index,
                    next_path=next_path,
                    total_depth=depth,
                    topology=topology,
                )
            )

        return RabbitHolePlan(
            instance_id=instance.instance_id,
            challenge_id=challenge_id,
            enabled=True,
            topology=topology,
            depth=depth,
            branching=branching,
            entry_route=entry_route,
            terminal_path=terminal_path,
            terminal_mode=terminal_mode,
            nodes=tuple(nodes),
        )

    def get_node(self, plan: RabbitHolePlan, path: str) -> RabbitHoleNode | None:
        """Resolve a route path to a node in the provided plan."""
        for node in plan.nodes:
            if node.path == path:
                return node
        return None

    def render_hop_page(self, plan: RabbitHolePlan, node: RabbitHoleNode) -> str:
        """Render one rabbit-hole hop page."""
        route_hint = _endpoint_hint(node.next_path)
        return render_template_string(
            self._template,
            title="Operations Console",
            heading="Diagnostic Workspace",
            current_hop=node.hop_index,
            next_path=node.next_path,
            route_hint=route_hint,
            remaining_hops=max(0, node.total_depth - (node.hop_index + 1)),
            instance_id=plan.instance_id,
            challenge_id=plan.challenge_id,
            topology=plan.topology,
            is_terminal=False,
        )

    def render_terminal_page(self, plan: RabbitHolePlan, next_path: str | None = None) -> str:
        """Render rabbit-hole terminal page."""
        route_hint = _endpoint_hint(next_path)
        return render_template_string(
            self._template,
            title="Completion Review",
            heading="Completion Review",
            current_hop=plan.depth,
            next_path=next_path,
            route_hint=route_hint,
            remaining_hops=0,
            instance_id=plan.instance_id,
            challenge_id=plan.challenge_id,
            topology=plan.topology,
            is_terminal=True,
        )
