"""
Tests for dynamic rabbit-hole planning and registration.
"""

from __future__ import annotations

import yaml
from flask import Flask

from deception_runtime import DeceptionRuntime
from deception_runtime.rabbit_holes import RabbitHoleManager
from deception_runtime.registry import DeceptionInstance


class _RecordingTelemetry:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event=None, **kwargs):
        if isinstance(event, dict):
            self.events.append(event)
            return
        payload = dict(kwargs)
        if "event_type" not in payload and event is not None:
            payload["event_type"] = event
        self.events.append(payload)

    def flush(self):
        return None


def _write_instance(tmp_path, instance_id: str, dynamic_cfg: dict | None = None):
    instance_data = {
        "id": instance_id,
        "_primitive_id": "test_primitive",
        "perception": {"channel": "dom", "surface": "html"},
        "payload": {"content_template": "payload"},
        "placement": {"route": "/"},
    }
    if dynamic_cfg is not None:
        instance_data["dynamic"] = dynamic_cfg

    instances_dir = tmp_path / "instances"
    instances_dir.mkdir(parents=True, exist_ok=True)
    path = instances_dir / f"{instance_id}.resolved.yaml"
    path.write_text(yaml.safe_dump(instance_data), encoding="utf-8")
    return instances_dir


def test_rabbit_hole_route_generation_is_deterministic():
    raw = {
        "id": "inst_001",
        "perception": {"channel": "dom", "surface": "html"},
        "payload": {"content_template": "payload"},
        "placement": {"route": "/"},
        "dynamic": {"enabled": True, "rabbit_hole": {"enabled": True, "depth": 3}},
    }
    instance = DeceptionInstance.from_dict(raw, "memory")
    manager = RabbitHoleManager(route_prefix="/_deception", max_depth=4, max_branching=1)

    plan_1 = manager.build_plan(instance, challenge_id="c1", synthesize_when_missing=False)
    plan_2 = manager.build_plan(instance, challenge_id="c1", synthesize_when_missing=False)

    assert plan_1 is not None
    assert plan_2 is not None
    assert plan_1.to_dict() == plan_2.to_dict()
    assert len(plan_1.nodes) == 3
    assert plan_1.entry_route == "/_deception/rabbit/hop/0"
    assert plan_1.terminal_path == "/_deception/rabbit/final"


def test_rabbit_hole_telemetry_hooks_invoked(tmp_path):
    instances_dir = _write_instance(
        tmp_path,
        "rabbit_telemetry_001",
        dynamic_cfg={
            "enabled": True,
            "rabbit_hole": {"enabled": True, "depth": 2},
        },
    )

    app = Flask(__name__)
    app.config.update(
        {
            "TESTING": True,
            "DECEPTIONS_ENABLED": True,
            "DECEPTIONS_FAIL_CLOSED": False,
            "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
            "DECEPTIONS_DYNAMIC_ENABLED": True,
            "DECEPTIONS_RABBIT_HOLES_ENABLED": True,
            "DECEPTIONS_FAKE_GOALS_ENABLED": False,
        }
    )

    @app.route("/")
    def index():
        return "ok"

    rt = DeceptionRuntime()
    rt.init_app(app)
    rt.telemetry = _RecordingTelemetry()

    client = app.test_client()
    client.get("/_deception/rabbit/hop/0")
    client.get("/_deception/rabbit/final")

    event_types = [event.get("event_type") for event in rt.telemetry.events]
    assert "rabbit_hole_entered" in event_types
    assert "rabbit_hole_hop" in event_types
    assert "rabbit_hole_terminal" in event_types


def test_rabbit_hole_collisions_skipped_when_fail_open(tmp_path):
    instance_id = "rabbit_collision_001"
    instances_dir = _write_instance(
        tmp_path,
        instance_id,
        dynamic_cfg={
            "enabled": True,
            "rabbit_hole": {"enabled": True, "depth": 2},
        },
    )

    app = Flask(__name__)
    app.config.update(
        {
            "TESTING": True,
            "DECEPTIONS_ENABLED": True,
            "DECEPTIONS_FAIL_CLOSED": False,
            "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
            "DECEPTIONS_DYNAMIC_ENABLED": True,
            "DECEPTIONS_RABBIT_HOLES_ENABLED": True,
            "DECEPTIONS_DYNAMIC_FAIL_OPEN": True,
        }
    )

    @app.route("/_deception/rabbit/hop/0")
    def real_collision_route():
        return "real-collision"

    @app.route("/")
    def index():
        return "ok"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()
    response = client.get("/_deception/rabbit/hop/0")
    assert response.status_code == 200
    assert response.data == b"real-collision"

    assert rt.dynamic_route_manager is not None
    assert rt.dynamic_route_manager.stats()["skipped_collisions"] >= 1


def test_rabbit_hole_plausible_route_style(tmp_path):
    instances_dir = _write_instance(
        tmp_path,
        "rabbit_plausible_001",
        dynamic_cfg={
            "enabled": True,
            "rabbit_hole": {"enabled": True, "depth": 2},
            "fake_goal": {"enabled": True},
        },
    )

    app = Flask(__name__)
    app.config.update(
        {
            "TESTING": True,
            "DECEPTIONS_ENABLED": True,
            "DECEPTIONS_FAIL_CLOSED": False,
            "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
            "DECEPTIONS_DYNAMIC_ENABLED": True,
            "DECEPTIONS_RABBIT_HOLES_ENABLED": True,
            "DECEPTIONS_FAKE_GOALS_ENABLED": True,
            "DECEPTIONS_DYNAMIC_ROUTE_STYLE": "plausible",
        }
    )

    @app.route("/")
    def index():
        return "ok"

    rt = DeceptionRuntime()
    rt.init_app(app)

    assert rt.dynamic_route_manager is not None
    stats = rt.dynamic_route_manager.stats()
    assert stats["route_style"] == "plausible"
    assert stats["rabbit_hole_routes"] >= 1
    assert stats["fake_goal_routes"] >= 1

    rabbit_paths = list(rt.dynamic_route_manager.registered_rabbit_routes)
    fake_goal_paths = list(rt.dynamic_route_manager.registered_fake_goal_routes)
    assert all(not path.startswith("/_deception/") for path in rabbit_paths)
    assert all(not path.startswith("/_deception/") for path in fake_goal_paths)

    client = app.test_client()
    response = client.get(rabbit_paths[0])
    assert response.status_code == 200
