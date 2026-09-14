"""Tests for plausible dynamic route catalog."""

from __future__ import annotations

from deception_runtime.dynamic_route_catalog import PlausibleDynamicRouteCatalog
from deception_runtime.registry import DeceptionInstance


def _instance(instance_id: str, endpoint_path: str | None = None) -> DeceptionInstance:
    data = {
        "id": instance_id,
        "perception": {"channel": "dom", "surface": "html"},
        "payload": {"content_template": ""},
        "placement": {"route": "/"},
    }
    if endpoint_path:
        data["honeytoken"] = {
            "enabled": True,
            "token_type": "url",
            "endpoint_path": endpoint_path,
        }
    return DeceptionInstance.from_dict(data, "memory")


def test_catalog_builds_deterministic_rabbit_routes() -> None:
    catalog = PlausibleDynamicRouteCatalog()
    instance = _instance("inst_001", endpoint_path="/console")

    first = catalog.build_rabbit_routes(instance=instance, challenge_id="c1", depth=2)
    second = catalog.build_rabbit_routes(instance=instance, challenge_id="c1", depth=2)

    assert first == second
    entry, hops, terminal = first
    assert entry == hops[0]
    assert len(hops) == 2
    assert all(path.startswith("/") for path in hops)
    assert terminal.startswith("/")


def test_catalog_uses_plausible_non_namespaced_paths() -> None:
    catalog = PlausibleDynamicRouteCatalog()
    instance = _instance("inst_002", endpoint_path="/debug/service")

    _, hops, terminal = catalog.build_rabbit_routes(instance=instance, challenge_id="c2", depth=2)
    goal = catalog.build_fake_goal_route(instance=instance, challenge_id="c2")

    assert all(not path.startswith("/_deception/") for path in hops)
    assert not terminal.startswith("/_deception/")
    assert not goal.startswith("/_deception/")
    assert any(path.startswith("/debug/") or path.startswith("/internal/") for path in hops)
