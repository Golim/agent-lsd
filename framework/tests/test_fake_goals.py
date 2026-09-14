"""
Tests for fake-goal planning and dynamic route registration.
"""

from __future__ import annotations

import yaml
from flask import Flask

from deception_runtime import DeceptionRuntime
from deception_runtime.fake_goals import FakeGoalManager
from deception_runtime.registry import DeceptionInstance


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


def test_fake_goal_path_and_flag_are_deterministic():
    raw = {
        "id": "fg_001",
        "perception": {"channel": "dom", "surface": "html"},
        "payload": {"content_template": "payload"},
        "placement": {"route": "/"},
        "dynamic": {"enabled": True, "fake_goal": {"enabled": True}},
    }
    instance = DeceptionInstance.from_dict(raw, "memory")
    manager = FakeGoalManager(route_prefix="/_deception", default_mode="both")

    plan_1 = manager.build_plan(instance, challenge_id="challenge-x", synthesize_when_missing=False)
    plan_2 = manager.build_plan(instance, challenge_id="challenge-x", synthesize_when_missing=False)

    assert plan_1 is not None
    assert plan_2 is not None
    assert plan_1.endpoint_path == "/_deception/goal"
    assert plan_1.fake_flag == plan_2.fake_flag
    assert plan_1.fake_flag is not None


def test_fake_goal_mode_supports_all_three_variants():
    manager = FakeGoalManager(route_prefix="/_deception", default_mode="both")
    base = {
        "id": "fg_modes",
        "perception": {"channel": "dom", "surface": "html"},
        "payload": {"content_template": "payload"},
        "placement": {"route": "/"},
        "dynamic": {"enabled": True, "fake_goal": {"enabled": True}},
    }

    # flag mode
    data = dict(base)
    data["dynamic"] = {"enabled": True, "fake_goal": {"enabled": True, "mode": "flag"}}
    plan = manager.build_plan(DeceptionInstance.from_dict(data, "memory"), "c", False)
    assert plan is not None and plan.fake_flag is not None and plan.success_message is None

    # success_message mode
    data = dict(base)
    data["dynamic"] = {"enabled": True, "fake_goal": {"enabled": True, "mode": "success_message"}}
    plan = manager.build_plan(DeceptionInstance.from_dict(data, "memory"), "c", False)
    assert plan is not None and plan.fake_flag is None and plan.success_message is not None

    # both mode
    data = dict(base)
    data["dynamic"] = {"enabled": True, "fake_goal": {"enabled": True, "mode": "both"}}
    plan = manager.build_plan(DeceptionInstance.from_dict(data, "memory"), "c", False)
    assert plan is not None and plan.fake_flag is not None and plan.success_message is not None


def test_fake_goal_routes_only_exist_when_enabled(tmp_path):
    instance_id = "fg_route_toggle_001"
    instances_dir = _write_instance(
        tmp_path,
        instance_id,
        dynamic_cfg={"enabled": True, "fake_goal": {"enabled": True}},
    )

    # Fake goals disabled globally: route must not exist.
    app_disabled = Flask(__name__)
    app_disabled.config.update(
        {
            "TESTING": True,
            "DECEPTIONS_ENABLED": True,
            "DECEPTIONS_FAIL_CLOSED": False,
            "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
            "DECEPTIONS_DYNAMIC_ENABLED": True,
            "DECEPTIONS_FAKE_GOALS_ENABLED": False,
            "DECEPTIONS_RABBIT_HOLES_ENABLED": False,
        }
    )

    @app_disabled.route("/")
    def index_disabled():
        return "ok"

    DeceptionRuntime().init_app(app_disabled)
    client_disabled = app_disabled.test_client()
    assert client_disabled.get("/_deception/goal").status_code == 404

    # Fake goals enabled globally: route exists.
    app_enabled = Flask(__name__)
    app_enabled.config.update(
        {
            "TESTING": True,
            "DECEPTIONS_ENABLED": True,
            "DECEPTIONS_FAIL_CLOSED": False,
            "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
            "DECEPTIONS_DYNAMIC_ENABLED": True,
            "DECEPTIONS_FAKE_GOALS_ENABLED": True,
            "DECEPTIONS_RABBIT_HOLES_ENABLED": False,
        }
    )

    @app_enabled.route("/")
    def index_enabled():
        return "ok"

    DeceptionRuntime().init_app(app_enabled)
    client_enabled = app_enabled.test_client()
    response = client_enabled.get("/_deception/goal")
    assert response.status_code == 200
    assert b"Receipt generated" in response.data
