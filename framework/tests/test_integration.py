"""
Integration test with sample instance file.
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def sample_instance():
    """Sample resolved instance data."""
    return {
        "id": "test_instance_001",
        "_primitive_id": "test_primitive",
        "perception": {
            "channel": "dom",
            "surface": "html",
            "human_visibility": "human_visible",
        },
        "payload": {
            "content_template": "This is a test payload",
            "type": "text",
        },
        "placement": {
            "route": "/",
            "selector": "body",
            "attribute": "data-test",
            "position": "append",
        },
    }


@pytest.fixture
def instances_dir(sample_instance, tmp_path):
    """Create temp directory with sample instance file."""
    import yaml

    instances_dir = tmp_path / "instances"
    instances_dir.mkdir()

    # Write sample instance
    instance_file = instances_dir / "test_instance_001.resolved.yaml"
    with open(instance_file, "w") as f:
        yaml.dump(sample_instance, f)

    return instances_dir


def test_registry_loads_instance(instances_dir):
    """Test registry loads instance from file."""
    from deception_runtime.registry import DeceptionRegistry

    registry = DeceptionRegistry(
        instances_dir=instances_dir,
        validate_schema=False,
    )

    assert len(registry) == 1
    assert "test_instance_001" in registry

    instance = registry.get("test_instance_001")
    assert instance is not None
    assert instance.instance_id == "test_instance_001"
    assert instance.channel == "dom"
    assert instance.surface == "html"
    assert instance.payload_text == "This is a test payload"
    assert instance.route == "/"


def test_registry_stats(instances_dir):
    """Test registry statistics."""
    from deception_runtime.registry import DeceptionRegistry

    registry = DeceptionRegistry(
        instances_dir=instances_dir,
        validate_schema=False,
    )

    stats = registry.stats()

    assert stats["total_instances"] == 1
    assert stats["total_routes"] == 1
    assert stats["by_channel"]["dom"] == 1
    assert stats["by_surface"]["html"] == 1


def test_extension_with_instances(instances_dir):
    """Test extension with real instance files."""
    from flask import Flask
    from deception_runtime import DeceptionRuntime

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_CHALLENGE_ID": "test_challenge",
        "DECEPTIONS_FAIL_CLOSED": False,
    })

    @app.route("/")
    def index():
        return "OK"

    rt = DeceptionRuntime()
    rt.init_app(app)

    assert rt.registry is not None
    assert len(rt.registry) == 1

    # Test health endpoint
    client = app.test_client()
    response = client.get("/__deception__/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["enabled"] is True
    assert data["registry_size"] == 1


def test_request_with_header(instances_dir):
    """Test request with X-Instance-Id header."""
    from flask import Flask, g
    from deception_runtime import DeceptionRuntime, get_active_instance

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_FAIL_CLOSED": False,
    })

    @app.route("/")
    def index():
        instance = get_active_instance()
        ctx = g.deception_ctx

        return {
            "ctx_enabled": ctx.enabled,
            "ctx_instance_id": ctx.instance_id,
            "instance_found": instance is not None,
        }

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Request with valid instance ID
    response = client.get("/", headers={"X-Instance-Id": "test_instance_001"})
    assert response.status_code == 200

    data = response.get_json()
    assert data["ctx_enabled"] is True
    assert data["ctx_instance_id"] == "test_instance_001"
    assert data["instance_found"] is True


def test_request_with_query(instances_dir):
    """Test request with ?instance= query parameter."""
    from flask import Flask, g
    from deception_runtime import DeceptionRuntime

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_FAIL_CLOSED": False,
    })

    @app.route("/")
    def index():
        ctx = g.deception_ctx
        return {
            "ctx_enabled": ctx.enabled,
            "ctx_instance_id": ctx.instance_id,
        }

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Request with query parameter
    response = client.get("/?instance=test_instance_001")
    assert response.status_code == 200

    data = response.get_json()
    assert data["ctx_enabled"] is True
    assert data["ctx_instance_id"] == "test_instance_001"


def test_fail_closed_invalid_instance(instances_dir):
    """Test fail_closed behavior with invalid instance."""
    from flask import Flask
    from deception_runtime import DeceptionRuntime

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_FAIL_CLOSED": True,  # Fail closed
    })

    @app.route("/")
    def index():
        return "OK"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Request with invalid instance ID
    response = client.get("/", headers={"X-Instance-Id": "invalid_instance"})
    assert response.status_code == 400
    assert b"Invalid deception instance" in response.data


def test_fail_open_invalid_instance(instances_dir):
    """Test fail_open behavior with invalid instance."""
    from flask import Flask, g
    from deception_runtime import DeceptionRuntime

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_FAIL_CLOSED": False,  # Fail open
    })

    @app.route("/")
    def index():
        ctx = g.deception_ctx
        return {
            "ctx_enabled": ctx.enabled,
        }

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Request with invalid instance ID - should succeed but be disabled
    response = client.get("/", headers={"X-Instance-Id": "invalid_instance"})
    assert response.status_code == 200

    data = response.get_json()
    assert data["ctx_enabled"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
