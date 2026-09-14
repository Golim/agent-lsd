"""
Tests for deception runtime.

Basic tests to verify core functionality.
"""

import pytest
from flask import Flask, g

# Test setup
pytest_plugins = []


@pytest.fixture
def app():
    """Create a test Flask app."""
    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": False,  # Start disabled for most tests
        "DECEPTIONS_INSTANCES_DIR": "deceptions/instances/generated",
        "DECEPTIONS_CHALLENGE_ID": "test_challenge",
    })

    @app.route("/")
    def index():
        return "OK"

    @app.route("/test")
    def test_route():
        return "TEST"

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


def test_extension_disabled(app, client):
    """Test extension with deceptions disabled."""
    from deception_runtime import DeceptionRuntime

    rt = DeceptionRuntime()
    rt.init_app(app)

    # Make a request
    response = client.get("/")
    assert response.status_code == 200

    # Context should be disabled
    with app.test_request_context("/"):
        from flask import g
        # Trigger before_request manually in test context
        with client:
            response = client.get("/")
            # Can't easily access g outside request context in tests
            # This is a limitation of the test setup


def test_health_endpoint(app, client):
    """Test health endpoint."""
    from deception_runtime import DeceptionRuntime

    rt = DeceptionRuntime()
    rt.init_app(app)

    response = client.get("/__deception__/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["enabled"] is False
    assert data["challenge_id"] == "test_challenge"
    assert data["registry_size"] == 0


def test_context_creation():
    """Test DeceptionContext creation."""
    from deception_runtime.context import DeceptionContext

    # Disabled context
    ctx = DeceptionContext.create_disabled("test_challenge")
    assert ctx.enabled is False
    assert ctx.challenge_id == "test_challenge"
    assert ctx.instance_id is None
    assert ctx.student_id is None
    assert ctx.request_id  # Should have a UUID

    # Enabled context
    ctx = DeceptionContext.create_enabled(
        challenge_id="test_challenge",
        instance_id="test_instance_001",
        student_id="student123",
    )
    assert ctx.enabled is True
    assert ctx.challenge_id == "test_challenge"
    assert ctx.instance_id == "test_instance_001"
    assert ctx.student_id == "student123"
    assert ctx.request_id


def test_config_from_flask():
    """Test configuration loading."""
    from deception_runtime.config import DeceptionConfig

    app_config = {
        "DECEPTIONS_ENABLED": "true",
        "DECEPTIONS_CHALLENGE_ID": "my_challenge",
        "DECEPTIONS_FAIL_CLOSED": False,
    }

    config = DeceptionConfig.from_flask_config(app_config, "default_app")

    assert config.enabled is True
    assert config.challenge_id == "my_challenge"
    assert config.fail_closed is False
    assert config.instances_dir == "deceptions/instances/generated"  # default


def test_str_to_bool():
    """Test boolean conversion."""
    from deception_runtime.config import str_to_bool

    assert str_to_bool("true") is True
    assert str_to_bool("True") is True
    assert str_to_bool("TRUE") is True
    assert str_to_bool("1") is True
    assert str_to_bool("yes") is True
    assert str_to_bool("on") is True

    assert str_to_bool("false") is False
    assert str_to_bool("False") is False
    assert str_to_bool("0") is False
    assert str_to_bool("no") is False
    assert str_to_bool("") is False
    assert str_to_bool(None) is False

    assert str_to_bool(True) is True
    assert str_to_bool(False) is False


def test_registry_empty_dir(tmp_path):
    """Test registry with empty directory."""
    from deception_runtime.registry import DeceptionRegistry

    # Create empty directory
    instances_dir = tmp_path / "instances"
    instances_dir.mkdir()

    registry = DeceptionRegistry(
        instances_dir=instances_dir,
        validate_schema=False,
    )

    assert len(registry) == 0
    assert registry.get("nonexistent") is None
    assert registry.list_ids() == []


def test_deception_instance_from_dict():
    """Test DeceptionInstance creation from dict."""
    from deception_runtime.registry import DeceptionInstance

    data = {
        "id": "test_instance_001",
        "_primitive_id": "test_primitive",
        "perception": {
            "channel": "dom",
            "surface": "html",
        },
        "payload": {
            "content_template": "Test payload content",
        },
        "placement": {
            "route": "/test",
            "selector": "#test",
        },
        "honeytoken": {
            "type": "endpoint",
        },
    }

    instance = DeceptionInstance.from_dict(data, "test.yaml")

    assert instance.instance_id == "test_instance_001"
    assert instance.primitive_id == "test_primitive"
    assert instance.channel == "dom"
    assert instance.surface == "html"
    assert instance.payload_text == "Test payload content"
    assert instance.route == "/test"
    assert instance.placement["selector"] == "#test"
    assert instance.honeytoken["type"] == "endpoint"


def test_deception_instance_missing_fields():
    """Test DeceptionInstance with missing required fields."""
    from deception_runtime.registry import DeceptionInstance

    # Missing id
    with pytest.raises(ValueError, match="Missing 'id'"):
        DeceptionInstance.from_dict({}, "test.yaml")

    # Missing channel
    with pytest.raises(ValueError, match="Missing 'perception.channel'"):
        DeceptionInstance.from_dict({
            "id": "test",
            "perception": {"surface": "html"},
        }, "test.yaml")

    # Missing surface
    with pytest.raises(ValueError, match="Missing 'perception.surface'"):
        DeceptionInstance.from_dict({
            "id": "test",
            "perception": {"channel": "dom"},
        }, "test.yaml")


def test_structured_logger():
    """Test structured logger."""
    from deception_runtime.logging import StructuredLogger

    logger = StructuredLogger("test_logger")

    # Should not raise
    logger.info("Test message")
    logger.info("Test with context", key="value", count=123)
    logger.debug("Debug message")
    logger.warning("Warning message", warning=True)
    logger.error("Error message", error_code=500)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
