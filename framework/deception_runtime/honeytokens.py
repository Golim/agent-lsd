"""
Honeytoken parsing, resolution, and matching.
"""

import re
from dataclasses import dataclass
from typing import Any

from deception_runtime.logging import StructuredLogger
from deception_runtime.registry import DeceptionInstance, DeceptionRegistry
from deception_runtime.trap_catalog import normalize_endpoint_path

logger = StructuredLogger(__name__)


@dataclass
class HoneytokenInfo:
    """Information about a resolved honeytoken."""

    instance_id: str
    token_type: str  # url, param, header, cookie, filename
    token_id_template: str
    paths: list[str]  # For URL honeytokens
    param_name: str | None  # For param honeytokens
    header_name: str | None  # For header honeytokens
    cookie_name: str | None  # For cookie honeytokens
    value_prefix: str | None  # Expected value prefix
    raw_honeytoken: dict[str, Any]


class HoneytokenMatcher:
    """
    Parses honeytokens from registry and provides matching capabilities.
    """

    def __init__(
        self,
        registry: DeceptionRegistry,
        protected_routes: list[str] | None = None,
        honeytoken_param: str = "ht",
        honeytoken_header: str = "X-Honeytoken",
        honeytoken_cookie: str = "ht",
        value_prefix: str = "",
    ):
        """
        Initialize honeytoken matcher.

        Args:
            registry: Deception registry
            protected_routes: List of real routes to avoid overriding
            honeytoken_param: Query parameter name for honeytokens
            honeytoken_header: Header name for honeytokens
            honeytoken_cookie: Cookie name for honeytokens
            value_prefix: Expected value prefix for param/header/cookie
        """
        self.registry = registry
        self.protected_routes = {
            normalize_endpoint_path(route) for route in (protected_routes or [])
        }
        self.honeytoken_param = honeytoken_param
        self.honeytoken_header = honeytoken_header
        self.honeytoken_cookie = honeytoken_cookie
        self.value_prefix = value_prefix

        # Parsed honeytokens
        self.honeytokens: list[HoneytokenInfo] = []

        # URL path -> list of instance_ids
        self.path_to_instances: dict[str, list[str]] = {}

        # Parse honeytokens from registry
        self._parse_honeytokens()

    def _extract_paths_from_instance(self, instance: DeceptionInstance) -> list[str]:
        """
        Extract monitored paths from an instance.

        Precedence:
        1. honeytoken.endpoint_path in raw
        2. placement.route if it looks like a decoy
        3. URL-like substring from payload.content_template

        Args:
            instance: Deception instance

        Returns:
            List of paths to monitor
        """
        paths = []

        # 1. Check honeytoken.endpoint_path
        if instance.honeytoken:
            endpoint_path = instance.honeytoken.get("endpoint_path")
            if endpoint_path:
                paths.append(normalize_endpoint_path(str(endpoint_path)))
                return paths

        # 2. Check placement.route (if not protected)
        if instance.route:
            normalized_route = normalize_endpoint_path(instance.route)
            if normalized_route not in self.protected_routes:
                paths.append(normalized_route)

        # 3. Extract URL-like patterns from payload
        if instance.payload_text:
            # Match URL patterns like /path/to/resource
            url_pattern = r'/[a-zA-Z0-9_\-/.~]+'
            matches = re.findall(url_pattern, instance.payload_text)

            for match in matches:
                # Filter out obviously invalid paths
                normalized_match = normalize_endpoint_path(match)
                if len(match) > 2 and normalized_match not in self.protected_routes:
                    if normalized_match not in paths:
                        paths.append(normalized_match)

        return paths

    def _parse_honeytokens(self) -> None:
        """Parse all honeytokens from registry."""
        logger.info("Parsing honeytokens from registry")

        parsed_count = 0
        url_count = 0
        unresolved_count = 0

        for instance_id in self.registry.list_ids():
            instance = self.registry.get(instance_id)
            if not instance:
                continue

            # Check if honeytoken is enabled
            if not instance.honeytoken or not instance.honeytoken.get("enabled"):
                continue

            token_type = instance.honeytoken.get("token_type", "url")
            token_id_template = instance.honeytoken.get(
                "token_id_template",
                f"studentless::{instance_id}",
            )

            # Parse based on type
            if token_type == "url":
                paths = self._extract_paths_from_instance(instance)

                if not paths:
                    logger.warning(
                        "URL honeytoken has no resolvable paths",
                        instance_id=instance_id,
                    )
                    unresolved_count += 1
                    continue

                honeytoken = HoneytokenInfo(
                    instance_id=instance_id,
                    token_type=token_type,
                    token_id_template=token_id_template,
                    paths=paths,
                    param_name=None,
                    header_name=None,
                    cookie_name=None,
                    value_prefix=None,
                    raw_honeytoken=instance.honeytoken,
                )

                self.honeytokens.append(honeytoken)

                # Index by path
                for path in paths:
                    if path not in self.path_to_instances:
                        self.path_to_instances[path] = []
                    self.path_to_instances[path].append(instance_id)

                url_count += 1
                parsed_count += 1

            elif token_type in {"param", "header", "cookie", "filename"}:
                # For param/header/cookie, we don't pre-index
                # They're checked passively in before_request
                honeytoken = HoneytokenInfo(
                    instance_id=instance_id,
                    token_type=token_type,
                    token_id_template=token_id_template,
                    paths=[],
                    param_name=self.honeytoken_param if token_type == "param" else None,
                    header_name=self.honeytoken_header if token_type == "header" else None,
                    cookie_name=self.honeytoken_cookie if token_type == "cookie" else None,
                    value_prefix=self.value_prefix,
                    raw_honeytoken=instance.honeytoken,
                )

                self.honeytokens.append(honeytoken)
                parsed_count += 1

        logger.info(
            "Honeytoken parsing complete",
            total=parsed_count,
            url=url_count,
            unresolved=unresolved_count,
            unique_paths=len(self.path_to_instances),
        )

    def match_url(self, path: str) -> list[str]:
        """
        Match a URL path to honeytoken instance IDs.

        Args:
            path: Request path

        Returns:
            List of matching instance IDs
        """
        normalized_path = normalize_endpoint_path(path)
        return self.path_to_instances.get(normalized_path, [])

    def match_param(self, value: str) -> list[str]:
        """
        Match a parameter value to honeytoken instance IDs.

        Args:
            value: Parameter value

        Returns:
            List of matching instance IDs
        """
        matches = []

        for ht in self.honeytokens:
            if ht.token_type != "param":
                continue

            # Check if value matches
            if self.value_prefix and not value.startswith(self.value_prefix):
                continue

            # Check if value contains instance_id
            if ht.instance_id in value or "studentless" in value:
                matches.append(ht.instance_id)

        return matches

    def match_header(self, value: str) -> list[str]:
        """
        Match a header value to honeytoken instance IDs.

        Args:
            value: Header value

        Returns:
            List of matching instance IDs
        """
        matches = []

        for ht in self.honeytokens:
            if ht.token_type != "header":
                continue

            # Check if value matches
            if self.value_prefix and not value.startswith(self.value_prefix):
                continue

            # Check if value contains instance_id
            if ht.instance_id in value or "studentless" in value:
                matches.append(ht.instance_id)

        return matches

    def match_cookie(self, value: str) -> list[str]:
        """
        Match a cookie value to honeytoken instance IDs.

        Args:
            value: Cookie value

        Returns:
            List of matching instance IDs
        """
        matches = []

        for ht in self.honeytokens:
            if ht.token_type != "cookie":
                continue

            # Check if value matches
            if self.value_prefix and not value.startswith(self.value_prefix):
                continue

            # Check if value contains instance_id
            if ht.instance_id in value or "studentless" in value:
                matches.append(ht.instance_id)

        return matches

    def get_url_paths(self) -> list[str]:
        """Get all URL paths that need honeytoken endpoints."""
        return sorted(self.path_to_instances.keys())

    def is_path_protected(self, path: str) -> bool:
        """Check if a path is in the protected routes list."""
        return path in self.protected_routes
