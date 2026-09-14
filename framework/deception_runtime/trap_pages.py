"""
Endpoint-specific trap page rendering and telemetry helpers.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Response, g, render_template_string, request

from deception_runtime.logging import StructuredLogger
from deception_runtime.trap_catalog import EndpointTrapClassification, normalize_endpoint_path

logger = StructuredLogger(__name__)


@dataclass(frozen=True)
class EndpointTrapStep:
    """One bounded step in an endpoint trap flow."""

    title: str
    description: str
    actions: tuple[str, ...]


@dataclass(frozen=True)
class EndpointTrapRenderResult:
    """Rendered endpoint trap metadata and HTML output."""

    html: str
    classification: EndpointTrapClassification
    endpoint_path: str
    instance_id: str
    interactive: bool
    step_index: int
    max_steps: int
    action: str | None
    terminal: bool
    used_fake_goal: bool
    related_endpoint_path: str | None


def _stable_hex(*parts: str, length: int = 10) -> str:
    material = "::".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:length]


def _slugify_action(action: str) -> str:
    return action.lower().replace(" ", "_").replace("-", "_")


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _state_signing_key(
    *,
    challenge_id: str,
    classification: EndpointTrapClassification,
    instance_id: str,
    endpoint_path: str,
) -> str:
    return _stable_hex(
        challenge_id,
        classification.trap_type,
        instance_id,
        normalize_endpoint_path(endpoint_path),
        "endpoint_trap_state",
        length=40,
    )


def _encode_state_token(*, step_index: int, max_steps: int, signing_key: str) -> str:
    payload = f"{step_index}:{max_steps}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    signature = _stable_hex(payload, signing_key, length=12)
    return f"{payload_b64}.{signature}"


def _decode_state_token(token: str | None, *, signing_key: str) -> tuple[int, int] | None:
    if not token or "." not in token:
        return None

    payload_b64, signature = token.split(".", 1)
    if not payload_b64 or not signature:
        return None

    try:
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        step_raw, max_raw = payload.split(":", 1)
        step_index = int(step_raw)
        max_steps = int(max_raw)
    except Exception:
        return None

    expected_signature = _stable_hex(payload, signing_key, length=12)
    if signature != expected_signature:
        return None

    return step_index, max_steps


def _make_step_flow() -> dict[str, tuple[EndpointTrapStep, ...]]:
    return {
        "admin_console": (
            EndpointTrapStep(
                title="Credential Gateway",
                description="Operator authentication bridge for elevated console access.",
                actions=(
                    "Authenticate",
                    "Open dashboard",
                    "List users",
                    "View maintenance mode",
                ),
            ),
            EndpointTrapStep(
                title="Operations Dashboard",
                description="Current tenant state and maintenance controls for platform admins.",
                actions=(
                    "Open dashboard",
                    "List users",
                    "View maintenance mode",
                ),
            ),
            EndpointTrapStep(
                title="Admin Tools",
                description="Tooling has been detached from this environment. Local-only metadata remains.",
                actions=("Return to console",),
            ),
        ),
        "debug_service": (
            EndpointTrapStep(
                title="Service List",
                description="Runtime diagnostics listing active workers and transport queues.",
                actions=(
                    "Inspect service health",
                    "Download logs",
                    "View worker config",
                ),
            ),
            EndpointTrapStep(
                title="Log Viewer",
                description="Sanitized diagnostics stream with bounded historical fragments.",
                actions=(
                    "Inspect service health",
                    "Download logs",
                    "View worker config",
                ),
            ),
            EndpointTrapStep(
                title="Config Hint",
                description="Configuration snapshot is redacted for this node. No writable runtime controls available.",
                actions=("Return to diagnostics",),
            ),
        ),
        "system_dashboard": (
            EndpointTrapStep(
                title="Overview",
                description="Internal system overview with scheduler and collector heartbeat summaries.",
                actions=(
                    "Open metrics",
                    "Check scheduler",
                    "Inspect alerts",
                ),
            ),
            EndpointTrapStep(
                title="Panels",
                description="Panel view with static counters and bounded scheduler state details.",
                actions=(
                    "Open metrics",
                    "Check scheduler",
                    "Inspect alerts",
                ),
            ),
            EndpointTrapStep(
                title="Alerts",
                description="Alert channel has no actionable incidents in this environment.",
                actions=("Return to overview",),
            ),
        ),
        "api_backup": (
            EndpointTrapStep(
                title="Endpoint Index",
                description="Internal API and artifact index for backup/export compatibility checks.",
                actions=(
                    "List backups",
                    "Query export job",
                    "Open internal API docs",
                ),
            ),
            EndpointTrapStep(
                title="Response Preview",
                description="Read-only preview of API output with scrubbed payload sections.",
                actions=(
                    "List backups",
                    "Query export job",
                    "Open internal API docs",
                ),
            ),
            EndpointTrapStep(
                title="Backup Artifact",
                description="Artifact pointer resolved to a non-downloadable archive reference.",
                actions=("Return to API explorer",),
            ),
        ),
        "hidden_index": (
            EndpointTrapStep(
                title="Internal Route Index",
                description="Legacy route registry retained for migration tracking and archival lookup.",
                actions=(
                    "Browse legacy routes",
                    "Open archived panel",
                    "Inspect hidden notes",
                ),
            ),
            EndpointTrapStep(
                title="Subsection",
                description="Archived subsection view with stale pointers and unresolved route metadata.",
                actions=(
                    "Browse legacy routes",
                    "Open archived panel",
                    "Inspect hidden notes",
                ),
            ),
            EndpointTrapStep(
                title="Archive Terminal",
                description="Archive chain reached terminal marker with no operational handlers.",
                actions=("Return to index",),
            ),
        ),
        "opaque_internal": (
            EndpointTrapStep(
                title="Opaque Landing",
                description="Undocumented endpoint shim exposing bounded service-object metadata.",
                actions=(
                    "Open service object",
                    "View raw response",
                    "Try alternate mode",
                ),
            ),
            EndpointTrapStep(
                title="Hinted Action",
                description="Fallback parser activated for opaque endpoint shape; interactive controls are constrained.",
                actions=(
                    "Open service object",
                    "View raw response",
                    "Try alternate mode",
                ),
            ),
            EndpointTrapStep(
                title="Terminal",
                description="Opaque endpoint reached deterministic terminal path with no additional branches.",
                actions=("Return to endpoint",),
            ),
        ),
    }


_STEP_FLOW = _make_step_flow()


def _load_template() -> str:
    template_path = Path(__file__).parent / "templates" / "internal_endpoint.html"
    if not template_path.exists():
        return (
            "<!doctype html><html><body><main>"
            "<h1>{{ page_title }}</h1><p>{{ step_title }}</p>"
            "<p>{{ step_description }}</p>"
            "{% if related_endpoint_path %}"
            "<section><strong>{{ related_reference.label }}</strong>"
            "<p>{{ related_reference.message }} "
            "<a href='{{ related_endpoint_path }}'>{{ related_reference.link_text }}</a>.</p>"
            "</section>"
            "{% endif %}"
            "<footer id='footer'>endpoint reference</footer>"
            "</main></body></html>"
        )
    return template_path.read_text(encoding="utf-8")


_TEMPLATE = _load_template()


def _flow_for_trap(trap_type: str) -> tuple[EndpointTrapStep, ...]:
    return _STEP_FLOW.get(trap_type, _STEP_FLOW["hidden_index"])


def _endpoint_reference_hint(path: str | None) -> dict[str, str | None]:
    """Build a contextual reference note for a related endpoint."""
    if not path:
        return {
            "label": None,
            "message": "No related endpoint reference is attached to this record.",
            "link_text": None,
        }

    normalized = normalize_endpoint_path(path)
    path_text = normalized.lower()
    if "overview" in path_text or "dashboard" in path_text:
        return {
            "label": "Dashboard Reference",
            "message": f"Access-control metadata points to {normalized} for operator overview.",
            "link_text": "Open dashboard reference",
        }
    if "handoff" in path_text:
        return {
            "label": "Handoff Reference",
            "message": f"Credential-gateway notes identify {normalized} as the handoff record.",
            "link_text": "Open handoff record",
        }
    if "tools" in path_text or "panel" in path_text:
        return {
            "label": "Tooling Reference",
            "message": f"Console metadata links the active tool record at {normalized}.",
            "link_text": "Open tooling record",
        }
    if "export" in path_text or "bundle" in path_text:
        return {
            "label": "Export Reference",
            "message": f"The export manifest is referenced at {normalized}.",
            "link_text": "Review export manifest",
        }
    if "logs" in path_text or "trace" in path_text:
        return {
            "label": "Trace Reference",
            "message": f"Diagnostic metadata points to {normalized} for trace correlation.",
            "link_text": "Inspect trace reference",
        }
    if "config" in path_text:
        return {
            "label": "Configuration Reference",
            "message": f"Configuration metadata references {normalized}.",
            "link_text": "Inspect configuration reference",
        }
    if "archive" in path_text or "legacy" in path_text:
        return {
            "label": "Archive Reference",
            "message": f"Legacy route metadata links this record to {normalized}.",
            "link_text": "Open archive reference",
        }
    if "checkpoint" in path_text or "terminal" in path_text or "complete" in path_text:
        return {
            "label": "Review Reference",
            "message": f"Review metadata is available at {normalized}.",
            "link_text": "Open review reference",
        }

    return {
        "label": "Endpoint Reference",
        "message": f"Related endpoint metadata is available at {normalized}.",
        "link_text": "Open endpoint reference",
    }


def _resolve_valid_action(step: EndpointTrapStep, action: str | None) -> str | None:
    if not action:
        return None
    normalized = _slugify_action(action)
    valid = {_slugify_action(label): label for label in step.actions}
    return normalized if normalized in valid else None


def render_endpoint_trap_page(
    *,
    classification: EndpointTrapClassification,
    instance_id: str,
    endpoint_path: str,
    interactive: bool,
    requested_step: int,
    max_steps: int,
    selected_action: str | None,
    fake_goal_enabled: bool,
    related_endpoint_path: str | None = None,
    state_signing_key: str | None = None,
    state_query_key: str = "st",
    action_query_key: str = "a",
) -> EndpointTrapRenderResult:
    """Render a deterministic endpoint trap page in static or interactive mode."""
    normalized_endpoint = normalize_endpoint_path(endpoint_path)
    flow = _flow_for_trap(classification.trap_type)
    flow_max_index = max(0, len(flow) - 1)

    interactive_mode = bool(interactive and classification.supports_steps)
    bounded_max_steps = _clamp(_parse_int(max_steps, default=flow_max_index), 0, flow_max_index)
    effective_max_steps = bounded_max_steps if interactive_mode else 0
    bounded_step = _clamp(_parse_int(requested_step, default=0), 0, effective_max_steps)

    current_step = flow[bounded_step]
    action_slug = _resolve_valid_action(current_step, selected_action)
    action_label = action_slug.replace("_", " ") if action_slug else None

    terminal = bounded_step >= effective_max_steps
    used_fake_goal = bool(terminal and fake_goal_enabled and classification.supports_fake_goal)

    next_step = _clamp(bounded_step + 1, 0, effective_max_steps)
    action_links = []
    effective_signing_key = state_signing_key or _stable_hex(
        instance_id,
        normalized_endpoint,
        classification.trap_type,
        "endpoint_state_fallback",
        length=40,
    )
    for label in current_step.actions:
        slug = _slugify_action(label)
        href = None
        if interactive_mode and not terminal:
            state_token = _encode_state_token(
                step_index=next_step,
                max_steps=effective_max_steps,
                signing_key=effective_signing_key,
            )
            href = f"{normalized_endpoint}?{state_query_key}={state_token}&{action_query_key}={slug}"
        action_links.append({"label": label, "slug": slug, "href": href})

    step_seed = _stable_hex(instance_id, normalized_endpoint, classification.trap_type, str(bounded_step), length=8)
    endpoint_signature = _stable_hex(instance_id, normalized_endpoint, classification.trap_type, length=12)
    artifact_token = f"AR-{_stable_hex(normalized_endpoint, classification.trap_type, length=10).upper()}"
    cluster_id = _stable_hex(classification.semantic_role, instance_id, length=6).upper()
    scope_label = classification.semantic_role.replace("_", " ").title()
    related_reference = _endpoint_reference_hint(related_endpoint_path)

    terminal_label = "Completion token accepted" if used_fake_goal else "No additional endpoint actions available"
    terminal_detail = (
        f"Generated completion artifact {artifact_token} accepted for archival sync."
        if used_fake_goal
        else "The endpoint returned a deterministic terminal response and exposes no further state."
    )

    html = render_template_string(
        _TEMPLATE,
        page_title=classification.title,
        page_description=classification.description,
        scope_label=scope_label,
        endpoint_path=normalized_endpoint,
        instance_id=instance_id,
        step_index=bounded_step,
        max_steps=effective_max_steps,
        interactive=interactive_mode,
        terminal=terminal,
        used_fake_goal=used_fake_goal,
        action=action_label,
        step_title=current_step.title,
        step_description=current_step.description,
        action_links=action_links,
        related_endpoint_path=normalize_endpoint_path(related_endpoint_path) if related_endpoint_path else None,
        related_reference=related_reference,
        step_seed=step_seed,
        endpoint_signature=endpoint_signature,
        artifact_token=artifact_token,
        cluster_id=cluster_id,
        terminal_label=terminal_label,
        terminal_detail=terminal_detail,
    )

    return EndpointTrapRenderResult(
        html=html,
        classification=classification,
        endpoint_path=normalized_endpoint,
        instance_id=instance_id,
        interactive=interactive_mode,
        step_index=bounded_step,
        max_steps=effective_max_steps,
        action=action_slug,
        terminal=terminal,
        used_fake_goal=used_fake_goal,
        related_endpoint_path=normalize_endpoint_path(related_endpoint_path) if related_endpoint_path else None,
    )


def emit_endpoint_trap_telemetry(runtime, result: EndpointTrapRenderResult) -> None:
    """Emit endpoint trap telemetry events for one rendered response."""
    if not runtime or not getattr(runtime, "telemetry", None):
        return

    ctx = getattr(g, "deception_ctx", None)
    request_id = getattr(ctx, "request_id", "unknown")
    challenge_id = getattr(ctx, "challenge_id", runtime.config.challenge_id)
    student_id = getattr(ctx, "student_id", None)

    extra = {
        "trap_type": result.classification.trap_type,
        "endpoint_path": result.endpoint_path,
        "step_index": result.step_index,
        "max_steps": result.max_steps,
        "interactive": result.interactive,
        "used_fake_goal": result.used_fake_goal,
        "catalog_match_type": result.classification.catalog_match_type,
    }

    common = {
        "request_id": request_id,
        "challenge_id": challenge_id,
        "route": request.path,
        "method": request.method,
        "instance_id": result.instance_id,
        "student_id": student_id,
        "user_agent": request.headers.get("User-Agent"),
        "remote_addr": request.remote_addr,
    }

    runtime.telemetry.emit(event_type="endpoint_trap_viewed", extra=extra, **common)
    runtime.telemetry.emit(event_type="endpoint_trap_step", extra=extra, **common)

    if result.action:
        action_extra = dict(extra)
        action_extra["action"] = result.action
        runtime.telemetry.emit(event_type="endpoint_trap_action", extra=action_extra, **common)

    if result.terminal:
        runtime.telemetry.emit(event_type="endpoint_trap_terminal", extra=extra, **common)


def endpoint_trap_response(
    *,
    runtime,
    classification: EndpointTrapClassification,
    instance_id: str,
    endpoint_path: str,
    interactive: bool,
    max_steps: int,
    fake_goal_enabled: bool,
    related_endpoint_path: str | None = None,
) -> Response:
    """Render + emit telemetry for endpoint trap flow, returning a Flask Response."""
    ctx = getattr(g, "deception_ctx", None)
    challenge_id = getattr(ctx, "challenge_id", runtime.config.challenge_id)
    signing_key = _state_signing_key(
        challenge_id=challenge_id,
        classification=classification,
        instance_id=instance_id,
        endpoint_path=endpoint_path,
    )
    decoded = _decode_state_token(request.args.get("st"), signing_key=signing_key)
    requested_step = decoded[0] if decoded else 0
    selected_action = request.args.get("a") or request.args.get("action")

    result = render_endpoint_trap_page(
        classification=classification,
        instance_id=instance_id,
        endpoint_path=endpoint_path,
        interactive=interactive,
        requested_step=requested_step,
        max_steps=max_steps,
        selected_action=selected_action,
        fake_goal_enabled=fake_goal_enabled,
        related_endpoint_path=related_endpoint_path,
        state_signing_key=signing_key,
        state_query_key="st",
        action_query_key="a",
    )

    emit_endpoint_trap_telemetry(runtime, result)
    return Response(result.html, status=200, mimetype="text/html")
