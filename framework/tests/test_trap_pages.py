"""Tests for endpoint trap page rendering and telemetry."""

from __future__ import annotations

from types import SimpleNamespace

from flask import Flask, g

from deception_runtime.context import DeceptionContext
from deception_runtime.trap_catalog import EndpointTrapClassifier
from deception_runtime.trap_pages import (
    emit_endpoint_trap_telemetry,
    endpoint_trap_response,
    render_endpoint_trap_page,
)


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


def test_each_trap_type_renders_successfully() -> None:
    app = Flask(__name__)
    classifier = EndpointTrapClassifier()

    mappings = [
        ("/console", "admin_console"),
        ("/debug/service", "debug_service"),
        ("/system/dashboard", "system_dashboard"),
        ("/panel/api_v1/backup", "api_backup"),
        ("/hidden", "hidden_index"),
        ("/45dfddb2", "opaque_internal"),
    ]

    with app.app_context():
        for path, trap_type in mappings:
            classification = classifier.classify(path)
            assert classification.trap_type == trap_type

            result = render_endpoint_trap_page(
                classification=classification,
                instance_id="inst_001",
                endpoint_path=path,
                interactive=True,
                requested_step=0,
                max_steps=2,
                selected_action=None,
                fake_goal_enabled=False,
            )

            assert "data-endpoint-path=" in result.html
            assert "id=\"footer\"" in result.html
            assert "id=\"status-badge\"" in result.html
            assert "id=\"overlay-layer\"" in result.html
            assert "template=" not in result.html
            assert "data-trap-type" not in result.html


def test_interactive_steps_are_bounded() -> None:
    app = Flask(__name__)
    classifier = EndpointTrapClassifier()

    with app.app_context():
        classification = classifier.classify("/console")
        result = render_endpoint_trap_page(
            classification=classification,
            instance_id="inst_001",
            endpoint_path="/console",
            interactive=True,
            requested_step=99,
            max_steps=99,
            selected_action=None,
            fake_goal_enabled=False,
        )

    assert result.step_index == 2
    assert result.max_steps == 2
    assert result.terminal is True


def test_static_mode_ignores_step_progression() -> None:
    app = Flask(__name__)
    classifier = EndpointTrapClassifier()

    with app.app_context():
        classification = classifier.classify("/debug/service")
        result = render_endpoint_trap_page(
            classification=classification,
            instance_id="inst_001",
            endpoint_path="/debug/service",
            interactive=False,
            requested_step=2,
            max_steps=2,
            selected_action="download_logs",
            fake_goal_enabled=False,
        )

    assert result.interactive is False
    assert result.step_index == 0
    assert result.max_steps == 0


def test_related_endpoint_reference_renders_contextual_hint() -> None:
    app = Flask(__name__)
    classifier = EndpointTrapClassifier()

    with app.app_context():
        classification = classifier.classify("/admin/console/login")
        result = render_endpoint_trap_page(
            classification=classification,
            instance_id="inst_001",
            endpoint_path="/admin/console/login",
            interactive=True,
            requested_step=0,
            max_steps=2,
            selected_action=None,
            fake_goal_enabled=False,
            related_endpoint_path="/dashboard/internal/overview",
        )

    assert result.related_endpoint_path == "/dashboard/internal/overview"
    assert "Dashboard Reference" in result.html
    assert "Open dashboard reference" in result.html
    assert "/dashboard/internal/overview" in result.html


def test_fake_goal_toggle_respected() -> None:
    app = Flask(__name__)
    classifier = EndpointTrapClassifier()

    with app.app_context():
        classification = classifier.classify("/panel/api_v1/backup")

        disabled = render_endpoint_trap_page(
            classification=classification,
            instance_id="inst_001",
            endpoint_path="/panel/api_v1/backup",
            interactive=True,
            requested_step=2,
            max_steps=2,
            selected_action="return_to_api_explorer",
            fake_goal_enabled=False,
        )

        enabled = render_endpoint_trap_page(
            classification=classification,
            instance_id="inst_001",
            endpoint_path="/panel/api_v1/backup",
            interactive=True,
            requested_step=2,
            max_steps=2,
            selected_action="return_to_api_explorer",
            fake_goal_enabled=True,
        )

    assert disabled.used_fake_goal is False
    assert enabled.used_fake_goal is True
    assert "Reference:" in enabled.html


def test_telemetry_fields_populated() -> None:
    app = Flask(__name__)
    classifier = EndpointTrapClassifier()
    telemetry = _RecordingTelemetry()

    runtime = SimpleNamespace(
        telemetry=telemetry,
        config=SimpleNamespace(challenge_id="challenge_test"),
    )

    with app.test_request_context("/panel/api_v1/backup?step=2&action=return_to_api_explorer"):
        g.deception_ctx = DeceptionContext.create_enabled(
            challenge_id="challenge_test",
            instance_id="inst_001",
            student_id="student_001",
        )
        result = render_endpoint_trap_page(
            classification=classifier.classify("/panel/api_v1/backup"),
            instance_id="inst_001",
            endpoint_path="/panel/api_v1/backup",
            interactive=True,
            requested_step=2,
            max_steps=2,
            selected_action="return_to_api_explorer",
            fake_goal_enabled=True,
        )

        emit_endpoint_trap_telemetry(runtime, result)

    event_types = [event["event_type"] for event in telemetry.events]
    assert "endpoint_trap_viewed" in event_types
    assert "endpoint_trap_step" in event_types
    assert "endpoint_trap_action" in event_types
    assert "endpoint_trap_terminal" in event_types

    for event in telemetry.events:
        extra = event["extra"]
        assert extra["trap_type"] == "api_backup"
        assert extra["endpoint_path"] == "/panel/api_v1/backup"
        assert extra["step_index"] == 2
        assert extra["max_steps"] == 2
        assert extra["interactive"] is True
        assert extra["used_fake_goal"] is True
        assert extra["catalog_match_type"] in {"exact", "pattern", "explicit", "fallback"}


def test_endpoint_trap_response_uses_opaque_state_token() -> None:
    app = Flask(__name__)
    classifier = EndpointTrapClassifier()
    telemetry = _RecordingTelemetry()
    runtime = SimpleNamespace(
        telemetry=telemetry,
        config=SimpleNamespace(challenge_id="challenge_test"),
    )

    with app.test_request_context("/console"):
        g.deception_ctx = DeceptionContext.create_enabled(
            challenge_id="challenge_test",
            instance_id="inst_opaque",
            student_id="student_001",
        )
        response = endpoint_trap_response(
            runtime=runtime,
            classification=classifier.classify("/console"),
            instance_id="inst_opaque",
            endpoint_path="/console",
            interactive=True,
            max_steps=2,
            fake_goal_enabled=False,
        )

    body = response.get_data(as_text=True)
    assert "?step=" not in body
    assert "&step=" not in body
    assert "?st=" in body
    assert ("&a=" in body) or ("&amp;a=" in body)
