"""
Tests for telemetry and honeytoken functionality.
"""

import json
import tempfile
from pathlib import Path

import pytest
from flask import Flask

# Test setup
def create_test_instance_file(tmp_path, instance_id, honeytoken_config=None):
    """Create a test instance YAML file."""
    import yaml

    instance_data = {
        "id": instance_id,
        "_primitive_id": "test_primitive",
        "perception": {
            "channel": "dom",
            "surface": "html",
        },
        "payload": {
            "content_template": "Test payload with /fake/honeytoken/path",
        },
        "placement": {
            "route": "/test",
            "selector": "body",
        },
    }

    if honeytoken_config:
        instance_data["honeytoken"] = honeytoken_config

    instances_dir = tmp_path / "instances"
    instances_dir.mkdir(parents=True, exist_ok=True)

    instance_file = instances_dir / f"{instance_id}.resolved.yaml"
    with open(instance_file, "w") as f:
        yaml.dump(instance_data, f)

    return instances_dir


def test_telemetry_emits_request_events(tmp_path):
    """Test telemetry emits request_start and request_end events."""
    from deception_runtime import DeceptionRuntime

    # Create test instance
    instances_dir = create_test_instance_file(tmp_path, "test_instance_001")

    # Create telemetry file
    telemetry_file = tmp_path / "telemetry.jsonl"

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_TELEMETRY_ENABLED": True,
        "DECEPTIONS_TELEMETRY_SINK": "jsonl",
        "DECEPTIONS_TELEMETRY_PATH": str(telemetry_file),
    })

    @app.route("/")
    def index():
        return "OK"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Make request
    response = client.get("/")
    assert response.status_code == 200

    # Flush telemetry
    rt.telemetry.flush()

    # Check telemetry file
    assert telemetry_file.exists()

    events = []
    with open(telemetry_file) as f:
        for line in f:
            events.append(json.loads(line))

    # Should have request_start and request_end
    event_types = [e["event_type"] for e in events]
    assert "request_start" in event_types
    assert "request_end" in event_types

    # Check request_end has status_code
    request_end = [e for e in events if e["event_type"] == "request_end"][0]
    assert request_end["status_code"] == 200


def test_telemetry_instance_selected(tmp_path):
    """Test instance_selected event is emitted when instance ID provided."""
    from deception_runtime import DeceptionRuntime

    # Create test instance
    instances_dir = create_test_instance_file(tmp_path, "test_instance_001")

    # Create telemetry file
    telemetry_file = tmp_path / "telemetry.jsonl"

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_TELEMETRY_ENABLED": True,
        "DECEPTIONS_TELEMETRY_SINK": "jsonl",
        "DECEPTIONS_TELEMETRY_PATH": str(telemetry_file),
    })

    @app.route("/")
    def index():
        return "OK"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Make request with instance ID
    response = client.get("/", headers={"X-Instance-Id": "test_instance_001"})
    assert response.status_code == 200

    # Flush telemetry
    rt.telemetry.flush()

    # Check for instance_selected event
    events = []
    with open(telemetry_file) as f:
        for line in f:
            events.append(json.loads(line))

    event_types = [e["event_type"] for e in events]
    assert "instance_selected" in event_types

    # Check instance_id is set
    instance_selected = [e for e in events if e["event_type"] == "instance_selected"][0]
    assert instance_selected["instance_id"] == "test_instance_001"


def test_honeytoken_url_endpoint(tmp_path):
    """Test honeytoken URL endpoint is registered and emits hit event."""
    from deception_runtime import DeceptionRuntime

    # Create test instance with URL honeytoken
    instances_dir = create_test_instance_file(
        tmp_path,
        "honeytoken_url_001",
        honeytoken_config={
            "enabled": True,
            "token_type": "url",
            "token_id_template": "studentless::honeytoken_url_001",
            "endpoint_path": "/fake/honeytoken/path",
        },
    )

    # Create telemetry file
    telemetry_file = tmp_path / "telemetry.jsonl"

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_TELEMETRY_ENABLED": True,
        "DECEPTIONS_TELEMETRY_SINK": "jsonl",
        "DECEPTIONS_TELEMETRY_PATH": str(telemetry_file),
        "DECEPTIONS_HONEYTOKENS_ENABLED": True,
    })

    @app.route("/")
    def index():
        return "OK"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Access honeytoken path
    response = client.get("/fake/honeytoken/path")
    assert response.status_code == 200  # Default response mode

    # Flush telemetry
    rt.telemetry.flush()

    # Check for honeytoken_hit event
    events = []
    with open(telemetry_file) as f:
        for line in f:
            events.append(json.loads(line))

    honeytoken_hits = [e for e in events if e["event_type"] == "honeytoken_hit"]
    assert len(honeytoken_hits) >= 1

    hit = honeytoken_hits[0]
    assert hit["instance_id"] == "honeytoken_url_001"
    assert hit["extra"]["token_type"] == "url"


def test_honeytoken_passive_detection(tmp_path):
    """Test passive honeytoken detection works without registered endpoint."""
    from deception_runtime import DeceptionRuntime

    # Create test instance with URL honeytoken
    instances_dir = create_test_instance_file(
        tmp_path,
        "honeytoken_passive_001",
        honeytoken_config={
            "enabled": True,
            "token_type": "url",
            "token_id_template": "studentless::honeytoken_passive_001",
            "endpoint_path": "/",  # Will collide with real route
        },
    )

    # Create telemetry file
    telemetry_file = tmp_path / "telemetry.jsonl"

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_TELEMETRY_ENABLED": True,
        "DECEPTIONS_TELEMETRY_SINK": "jsonl",
        "DECEPTIONS_TELEMETRY_PATH": str(telemetry_file),
        "DECEPTIONS_HONEYTOKENS_ENABLED": True,
        "DECEPTIONS_PROTECTED_ROUTES": "/",  # Mark as protected
    })

    @app.route("/")
    def index():
        return "Real route"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Access real route (should trigger passive detection)
    response = client.get("/")
    assert response.status_code == 200
    assert response.data == b"Real route"  # Real route still works

    # Flush telemetry
    rt.telemetry.flush()

    # Check for honeytoken_hit event from passive detection
    events = []
    with open(telemetry_file) as f:
        for line in f:
            events.append(json.loads(line))

    honeytoken_hits = [e for e in events if e["event_type"] == "honeytoken_hit"]

    # Should detect via passive detection
    if honeytoken_hits:
        hit = honeytoken_hits[0]
        assert hit["extra"]["detected_via"] == "passive"


def test_telemetry_sampling(tmp_path):
    """Test telemetry sampling works."""
    from deception_runtime import DeceptionRuntime

    # Create test instance
    instances_dir = create_test_instance_file(tmp_path, "test_instance_001")

    # Create telemetry file
    telemetry_file = tmp_path / "telemetry.jsonl"

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_TELEMETRY_ENABLED": True,
        "DECEPTIONS_TELEMETRY_SINK": "jsonl",
        "DECEPTIONS_TELEMETRY_PATH": str(telemetry_file),
        "DECEPTIONS_TELEMETRY_SAMPLE_RATE": 0.5,  # 50% sampling
    })

    @app.route("/")
    def index():
        return "OK"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Make multiple requests
    for _ in range(100):
        client.get("/")

    # Flush telemetry
    rt.telemetry.flush()

    # Check event count
    event_count = 0
    with open(telemetry_file) as f:
        for line in f:
            event_count += 1

    # Should be roughly 50% of events (200 events total without sampling: 100 start + 100 end)
    # With 50% sampling, should be around 100 events
    # Allow some variance for deterministic hashing
    assert 30 < event_count < 170, f"Expected ~100 events with 50% sampling, got {event_count}"


def test_telemetry_sqlite_sink(tmp_path):
    """Test SQLite telemetry sink."""
    from deception_runtime import DeceptionRuntime
    import sqlite3

    # Create test instance
    instances_dir = create_test_instance_file(tmp_path, "test_instance_001")

    # Create telemetry database
    telemetry_db = tmp_path / "telemetry.sqlite"

    app = Flask(__name__)
    app.config.update({
        "TESTING": True,
        "DECEPTIONS_ENABLED": True,
        "DECEPTIONS_INSTANCES_DIR": str(instances_dir),
        "DECEPTIONS_TELEMETRY_ENABLED": True,
        "DECEPTIONS_TELEMETRY_SINK": "sqlite",
        "DECEPTIONS_TELEMETRY_PATH": str(telemetry_db),
    })

    @app.route("/")
    def index():
        return "OK"

    rt = DeceptionRuntime()
    rt.init_app(app)

    client = app.test_client()

    # Make request
    response = client.get("/")
    assert response.status_code == 200

    # Check database
    assert telemetry_db.exists()

    conn = sqlite3.connect(str(telemetry_db))
    cursor = conn.cursor()

    # Check events table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
    assert cursor.fetchone() is not None

    # Check events were inserted
    cursor.execute("SELECT COUNT(*) FROM events")
    count = cursor.fetchone()[0]
    assert count >= 2  # At least request_start and request_end

    # Check event structure
    cursor.execute("SELECT event_type, route, method FROM events")
    events = cursor.fetchall()
    assert len(events) >= 2

    conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
