"""
Deterministic fake-goal plan generation and rendering.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flask import render_template_string

from deception_runtime.logging import StructuredLogger
from deception_runtime.registry import DeceptionInstance

if TYPE_CHECKING:
    from deception_runtime.dynamic_route_catalog import PlausibleDynamicRouteCatalog

logger = StructuredLogger(__name__)


def _mode_has_flag(mode: str) -> bool:
    return mode in {"flag", "both"}


def _mode_has_success(mode: str) -> bool:
    return mode in {"success_message", "both"}


def _normalize_mode(mode: str | None, default: str) -> str:
    allowed = {"flag", "success_message", "both"}
    value = (mode or default).strip().lower()
    return value if value in allowed else default


@dataclass(frozen=True)
class FakeGoalPlan:
    """Deterministic fake-goal route plan for one instance."""

    instance_id: str
    challenge_id: str
    enabled: bool
    endpoint_path: str
    mode: str
    fake_flag: str | None
    success_message: str | None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe plan structure."""
        return {
            "instance_id": self.instance_id,
            "challenge_id": self.challenge_id,
            "enabled": self.enabled,
            "endpoint_path": self.endpoint_path,
            "mode": self.mode,
            "fake_flag": self.fake_flag,
            "success_message": self.success_message,
        }


class FakeGoalManager:
    """Build and render fake-goal plans with deterministic outputs."""

    def __init__(
        self,
        route_prefix: str = "/_deception",
        default_mode: str = "both",
        route_style: str = "namespaced",
        route_catalog: "PlausibleDynamicRouteCatalog | None" = None,
    ):
        self.route_prefix = route_prefix
        self.default_mode = _normalize_mode(default_mode, default="both")
        self.route_style = route_style if route_style in {"namespaced", "plausible"} else "namespaced"
        self.route_catalog = route_catalog
        self._template = self._load_template()

    def _load_template(self) -> str:
        template_path = Path(__file__).parent / "templates" / "submission_receipt.html"
        if not template_path.exists():
            return (
                "<!doctype html><html><head><title>Submission Result</title></head>"
                "<body><h1>Submission accepted</h1>{% if fake_flag %}<pre>{{ fake_flag }}</pre>{% endif %}"
                "{% if success_message %}<p>{{ success_message }}</p>{% endif %}</body></html>"
            )
        return template_path.read_text(encoding="utf-8")

    def _instance_hex_suffix(self, instance: DeceptionInstance, challenge_id: str) -> str:
        material = f"{challenge_id}:{instance.instance_id}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]

    def generate_fake_flag(
        self,
        instance: DeceptionInstance,
        challenge_id: str,
        fake_flag_template: str | None = None,
    ) -> str:
        """Generate a deterministic, plausible decoy flag."""
        hex_suffix = self._instance_hex_suffix(instance, challenge_id)

        if fake_flag_template:
            try:
                fake_flag = fake_flag_template.format(
                    hex_suffix=hex_suffix,
                    instance_id=instance.instance_id,
                    challenge_id=challenge_id,
                )
            except Exception:
                fake_flag = fake_flag_template.replace("{hex_suffix}", hex_suffix)
        else:
            stems = (
                "ops_ticket",
                "auth_token",
                "build_manifest",
                "export_bundle",
                "access_key",
            )
            stem_index = int(hashlib.sha256(f"{challenge_id}:{instance.instance_id}".encode("utf-8")).hexdigest()[:2], 16)
            stem = stems[stem_index % len(stems)]
            fake_flag = f"CTF{{{stem}_{hex_suffix}}}"

        # Safety guard: keep decoy distinct from payload text if payload resembles a flag.
        if fake_flag.strip() == (instance.payload_text or "").strip():
            fake_flag = f"CTF{{access_key_{hex_suffix}x}}"

        return fake_flag

    def fake_flag_hash(self, fake_flag: str | None) -> str | None:
        """Hash fake flag for telemetry without storing raw values."""
        if not fake_flag:
            return None
        return hashlib.sha256(fake_flag.encode("utf-8")).hexdigest()[:16]

    def build_plan(
        self,
        instance: DeceptionInstance,
        challenge_id: str,
        synthesize_when_missing: bool = False,
    ) -> FakeGoalPlan | None:
        """Build fake-goal plan for an instance, or None if disabled."""
        dynamic_cfg = instance.raw.get("dynamic", {})
        if not isinstance(dynamic_cfg, dict):
            dynamic_cfg = {}

        instance_dynamic_enabled = dynamic_cfg.get("enabled")
        if instance_dynamic_enabled is False:
            return None

        fake_goal_cfg = dynamic_cfg.get("fake_goal", {})
        if not isinstance(fake_goal_cfg, dict):
            fake_goal_cfg = {}

        enabled_value = fake_goal_cfg.get("enabled")
        if enabled_value is None:
            enabled_value = synthesize_when_missing
        if not bool(enabled_value):
            return None

        mode = _normalize_mode(fake_goal_cfg.get("mode"), default=self.default_mode)

        configured_endpoint_path = str(fake_goal_cfg.get("endpoint_path") or "").strip()
        if configured_endpoint_path:
            endpoint_path = configured_endpoint_path
        elif self.route_style == "plausible" and self.route_catalog:
            endpoint_path = self.route_catalog.build_fake_goal_route(
                instance=instance,
                challenge_id=challenge_id,
            )
        else:
            endpoint_path = f"{self.route_prefix}/goal"

        if self.route_style == "namespaced":
            if not endpoint_path.startswith(f"{self.route_prefix}/"):
                logger.warning(
                    "Fake-goal endpoint must stay namespaced; using deterministic default",
                    instance_id=instance.instance_id,
                    endpoint_path=endpoint_path,
                    route_prefix=self.route_prefix,
                )
                endpoint_path = f"{self.route_prefix}/goal"
        elif not endpoint_path.startswith("/"):
            logger.warning(
                "Fake-goal endpoint must be an absolute path; using deterministic plausible route",
                instance_id=instance.instance_id,
                endpoint_path=endpoint_path,
            )
            endpoint_path = self.route_catalog.build_fake_goal_route(
                instance=instance,
                challenge_id=challenge_id,
            ) if self.route_catalog else f"{self.route_prefix}/goal"

        fake_flag = None
        if _mode_has_flag(mode):
            fake_flag_template = fake_goal_cfg.get("fake_flag_template")
            fake_flag = self.generate_fake_flag(instance, challenge_id, fake_flag_template=fake_flag_template)

        success_message = None
        if _mode_has_success(mode):
            success_message = str(
                fake_goal_cfg.get("success_message")
                or "Success."
            )

        return FakeGoalPlan(
            instance_id=instance.instance_id,
            challenge_id=challenge_id,
            enabled=True,
            endpoint_path=endpoint_path,
            mode=mode,
            fake_flag=fake_flag,
            success_message=success_message,
        )

    def render_page(self, plan: FakeGoalPlan, rabbit_hole_terminal: bool = False) -> str:
        """Render fake-goal page."""
        return render_template_string(
            self._template,
            title="Submission Receipt",
            heading="Result Summary",
            fake_flag=plan.fake_flag if _mode_has_flag(plan.mode) else None,
            success_message=plan.success_message if _mode_has_success(plan.mode) else None,
            endpoint_path=plan.endpoint_path,
            instance_id=plan.instance_id,
            challenge_id=plan.challenge_id,
            rabbit_hole_terminal=rabbit_hole_terminal,
        )

    def mode_has_flag(self, mode: str) -> bool:
        return _mode_has_flag(mode)

    def mode_has_success(self, mode: str) -> bool:
        return _mode_has_success(mode)
