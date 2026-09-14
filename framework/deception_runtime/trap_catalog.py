"""
Endpoint trap catalog and deterministic endpoint classification.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from deception_runtime.logging import StructuredLogger

logger = StructuredLogger(__name__)


def normalize_endpoint_path(path: str | None) -> str:
    """Normalize endpoint path to a deterministic form."""
    value = (path or "").strip()
    if not value:
        return "/"
    if not value.startswith("/"):
        value = f"/{value}"
    if len(value) > 1 and value.endswith("/"):
        value = value[:-1]
    return value.lower()


@dataclass(frozen=True)
class TrapCatalogEntry:
    """One predefined endpoint trap archetype."""

    trap_type: str
    path_patterns: tuple[str, ...]
    template_name: str
    semantic_role: str
    default_title: str
    default_description: str
    default_interaction_mode: str
    telemetry_tags: tuple[str, ...]
    supports_fake_goal: bool
    supports_steps: bool


@dataclass(frozen=True)
class EndpointTrapClassification:
    """Classification output consumed by trap rendering."""

    trap_type: str
    endpoint_path: str
    template_name: str
    semantic_role: str
    title: str
    description: str
    interaction_mode: str
    telemetry_tags: tuple[str, ...]
    supports_fake_goal: bool
    supports_steps: bool
    catalog_match_type: str


def _is_regex_pattern(pattern: str) -> bool:
    return pattern.startswith("re:")


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    source = pattern[3:] if pattern.startswith("re:") else f"^{re.escape(pattern)}$"
    return re.compile(source)


def _default_entries(opaque_patterns: Iterable[str] | None = None) -> tuple[TrapCatalogEntry, ...]:
    extra_opaque_patterns = [p.strip() for p in (opaque_patterns or []) if str(p).strip()]
    opaque_catalog_patterns = ["re:^/[a-f0-9]{8,}$", "re:^/[a-z0-9]{8,16}$"]
    for pattern in extra_opaque_patterns:
        opaque_catalog_patterns.append(f"re:{pattern}" if not pattern.startswith("re:") else pattern)

    return (
        TrapCatalogEntry(
            trap_type="admin_console",
            path_patterns=(
                "/console",
                "/admin",
                "/admin/panel",
                "/dashboard",
                "/control",
                "re:^/(admin|console|dashboard|control)(?:/.*)?$",
            ),
            template_name="admin_console_panel.html",
            semantic_role="internal_admin_console",
            default_title="Administration Console",
            default_description="Restricted management workspace for privileged operators.",
            default_interaction_mode="interactive",
            telemetry_tags=("admin", "console", "privileged"),
            supports_fake_goal=True,
            supports_steps=True,
        ),
        TrapCatalogEntry(
            trap_type="debug_service",
            path_patterns=(
                "/debug",
                "/debug/service",
                "/debug/console",
                "/internal/status",
                "/status",
                "/health",
                "re:^/(debug|status|health)(?:/.*)?$",
            ),
            template_name="service_diagnostics.html",
            semantic_role="service_debug",
            default_title="Service Diagnostics",
            default_description="Internal service diagnostics and worker inspection panel.",
            default_interaction_mode="interactive",
            telemetry_tags=("debug", "service", "diagnostics"),
            supports_fake_goal=False,
            supports_steps=True,
        ),
        TrapCatalogEntry(
            trap_type="system_dashboard",
            path_patterns=(
                "/system/dashboard",
                "/system",
                "/internal/dashboard",
                "re:^/system(?:/.*)?$",
            ),
            template_name="system_dashboard_view.html",
            semantic_role="system_dashboard",
            default_title="System Dashboard",
            default_description="Operational view for internal monitoring and control metrics.",
            default_interaction_mode="interactive",
            telemetry_tags=("system", "dashboard", "monitoring"),
            supports_fake_goal=False,
            supports_steps=True,
        ),
        TrapCatalogEntry(
            trap_type="api_backup",
            path_patterns=(
                "/panel/api_v1/backup",
                "/backup",
                "/api/internal",
                "/export",
                "/data",
                "/internal/api/docs",
                "re:^/(backup|export|data|api/internal)(?:/.*)?$",
                "re:^/panel/api_v1/backup(?:/.*)?$",
            ),
            template_name="api_backup_explorer.html",
            semantic_role="api_backup_explorer",
            default_title="Backup and Export Explorer",
            default_description="Internal API explorer and backup artifact management panel.",
            default_interaction_mode="interactive",
            telemetry_tags=("api", "backup", "export"),
            supports_fake_goal=True,
            supports_steps=True,
        ),
        TrapCatalogEntry(
            trap_type="hidden_index",
            path_patterns=(
                "/hidden",
                "/private",
                "/internal",
                "/legacy",
                "/old-admin",
                "re:^/(hidden|private|internal|legacy|old-admin)(?:/.*)?$",
            ),
            template_name="internal_index_view.html",
            semantic_role="hidden_route_index",
            default_title="Archived Internal Index",
            default_description="Legacy index of internal routes retained for compatibility audits.",
            default_interaction_mode="interactive",
            telemetry_tags=("hidden", "legacy", "index"),
            supports_fake_goal=True,
            supports_steps=True,
        ),
        TrapCatalogEntry(
            trap_type="opaque_internal",
            path_patterns=tuple(opaque_catalog_patterns),
            template_name="opaque_service_endpoint.html",
            semantic_role="opaque_internal_endpoint",
            default_title="Undocumented Service Endpoint",
            default_description="Undocumented endpoint for internal service object and raw response debugging.",
            default_interaction_mode="interactive",
            telemetry_tags=("opaque", "internal", "undocumented"),
            supports_fake_goal=False,
            supports_steps=True,
        ),
    )


class EndpointTrapClassifier:
    """Deterministic classifier for endpoint trap archetypes."""

    def __init__(
        self,
        *,
        explicit_map: dict[str, str] | None = None,
        map_file_path: str | None = None,
        opaque_patterns: list[str] | None = None,
    ):
        self.entries = _default_entries(opaque_patterns)
        self._catalog = {entry.trap_type: entry for entry in self.entries}
        self._fallback = self._catalog["hidden_index"]
        self._exact_index: dict[str, TrapCatalogEntry] = {}
        self._pattern_index: list[tuple[TrapCatalogEntry, re.Pattern[str]]] = []
        self._explicit_map: dict[str, str] = {}

        self._build_indexes()
        self._load_explicit_map(explicit_map=explicit_map, map_file_path=map_file_path)

    def _build_indexes(self) -> None:
        for entry in self.entries:
            for pattern in entry.path_patterns:
                if _is_regex_pattern(pattern):
                    self._pattern_index.append((entry, _compile_pattern(pattern)))
                else:
                    self._exact_index[normalize_endpoint_path(pattern)] = entry

    def _register_map_entry(self, path: str, trap_type: str) -> None:
        normalized_path = normalize_endpoint_path(path)
        normalized_type = str(trap_type or "").strip()
        if normalized_type not in self._catalog:
            logger.warning(
                "Ignoring invalid endpoint trap map entry",
                endpoint_path=normalized_path,
                trap_type=normalized_type,
            )
            return
        self._explicit_map[normalized_path] = normalized_type

    def _load_explicit_map(self, *, explicit_map: dict[str, str] | None, map_file_path: str | None) -> None:
        if explicit_map:
            for path, trap_type in explicit_map.items():
                self._register_map_entry(path, trap_type)

        if not map_file_path:
            return

        path_obj = Path(map_file_path)
        if not path_obj.exists():
            logger.warning("Endpoint trap map file not found", map_file_path=str(path_obj))
            return

        try:
            with open(path_obj, encoding="utf-8") as f:
                loaded = json.load(f)
        except Exception as exc:
            logger.warning(
                "Failed to load endpoint trap map file",
                map_file_path=str(path_obj),
                error=str(exc),
            )
            return

        if not isinstance(loaded, dict):
            logger.warning(
                "Endpoint trap map file must contain a JSON object",
                map_file_path=str(path_obj),
            )
            return

        for path, trap_type in loaded.items():
            self._register_map_entry(str(path), str(trap_type))

    def _classification_from_entry(
        self,
        entry: TrapCatalogEntry,
        endpoint_path: str,
        match_type: str,
    ) -> EndpointTrapClassification:
        return EndpointTrapClassification(
            trap_type=entry.trap_type,
            endpoint_path=endpoint_path,
            template_name=entry.template_name,
            semantic_role=entry.semantic_role,
            title=entry.default_title,
            description=entry.default_description,
            interaction_mode=entry.default_interaction_mode,
            telemetry_tags=entry.telemetry_tags,
            supports_fake_goal=entry.supports_fake_goal,
            supports_steps=entry.supports_steps,
            catalog_match_type=match_type,
        )

    def classify(self, endpoint_path: str) -> EndpointTrapClassification:
        """
        Classify an endpoint path with deterministic precedence.

        Precedence: explicit map -> exact catalog -> pattern catalog -> fallback.
        """
        normalized_path = normalize_endpoint_path(endpoint_path)

        explicit_type = self._explicit_map.get(normalized_path)
        if explicit_type:
            return self._classification_from_entry(
                self._catalog[explicit_type],
                endpoint_path=normalized_path,
                match_type="explicit",
            )

        exact_match = self._exact_index.get(normalized_path)
        if exact_match:
            return self._classification_from_entry(
                exact_match,
                endpoint_path=normalized_path,
                match_type="exact",
            )

        for entry, compiled in self._pattern_index:
            if compiled.match(normalized_path):
                return self._classification_from_entry(
                    entry,
                    endpoint_path=normalized_path,
                    match_type="pattern",
                )

        return self._classification_from_entry(
            self._fallback,
            endpoint_path=normalized_path,
            match_type="fallback",
        )
