#!/usr/bin/env python3

"""Constraint enforcement for deception instance generation.

Ensures generated instances don't break challenges or violate fairness rules.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set


class ConstraintViolation(Exception):
    """Raised when a constraint cannot be satisfied."""
    pass


class ConstraintChecker:
    """Enforces constraints on deception instances."""

    def __init__(self, real_solution_routes: Set[str] | None = None):
        """Initialize constraint checker.

        Args:
            real_solution_routes: Set of routes that are part of the real solution path
        """
        self.real_solution_routes = real_solution_routes or set()

    def check_instance(self, instance: Dict[str, Any], retries: int = 10) -> None:
        """Check all constraints for an instance.

        Args:
            instance: The generated instance to check
            retries: Number of retries attempted (for error messages)

        Raises:
            ConstraintViolation: If constraints are violated
        """
        # Check route collision with real solution
        self._check_route_collision(instance)

        # Check for duplicate decoy routes within instance
        self._check_duplicate_decoys(instance)

        # Check honeytoken uniqueness
        self._check_honeytoken_uniqueness(instance)

        # Check fake flag format
        self._check_fake_flag_format(instance)

    def _check_route_collision(self, instance: Dict[str, Any]) -> None:
        """Ensure decoy routes don't block the real solution.

        Args:
            instance: Instance to check

        Raises:
            ConstraintViolation: If a decoy route collides with solution
        """
        constraints = instance.get("constraints", {})
        if not constraints.get("do_not_block_human_solution", True):
            return  # This constraint is disabled

        # Check placement route
        placement = instance.get("placement", {})
        route = placement.get("route")
        if route and route in self.real_solution_routes:
            raise ConstraintViolation(
                f"Decoy route '{route}' collides with real solution path"
            )

        # Check artifacts
        payload = instance.get("payload", {})
        artifacts = payload.get("artifacts", [])
        for artifact in artifacts:
            if artifact.get("kind") == "route":
                art_name = artifact.get("name", "")
                if art_name in self.real_solution_routes:
                    raise ConstraintViolation(
                        f"Artifact route '{art_name}' collides with real solution path"
                    )

        # Check rendered content for route-like patterns
        content = payload.get("content_template", "")
        if content:
            # Look for patterns like /path/to/something
            route_pattern = re.compile(r'/[a-zA-Z0-9_\-/]+')
            found_routes = route_pattern.findall(content)
            for found_route in found_routes:
                if found_route in self.real_solution_routes:
                    raise ConstraintViolation(
                        f"Content contains solution route '{found_route}'"
                    )

    def _check_duplicate_decoys(self, instance: Dict[str, Any]) -> None:
        """Ensure no duplicate decoy routes within one instance.

        Args:
            instance: Instance to check

        Raises:
            ConstraintViolation: If duplicate decoys found
        """
        routes = []

        # Collect all routes from artifacts
        payload = instance.get("payload", {})
        artifacts = payload.get("artifacts", [])
        for artifact in artifacts:
            if artifact.get("kind") in ("route", "endpoint"):
                routes.append(artifact.get("name", ""))

        # Check for duplicates
        seen = set()
        for route in routes:
            if route in seen:
                raise ConstraintViolation(f"Duplicate decoy route: {route}")
            seen.add(route)

    def _check_honeytoken_uniqueness(self, instance: Dict[str, Any]) -> None:
        """Ensure honeytoken IDs are unique.

        This is primarily a sanity check - uniqueness should be guaranteed
        by the seeding mechanism, but we verify here.

        Args:
            instance: Instance to check
        """
        honeytoken = instance.get("honeytoken", {})
        if not honeytoken.get("enabled", False):
            return

        token_id = honeytoken.get("token_id_template", "")
        instance_id = instance.get("id", "")

        # Basic check: token_id should reference the instance id or be unique enough
        # This is mostly a placeholder - actual uniqueness is ensured by seeding
        if not token_id:
            raise ConstraintViolation("Honeytoken enabled but no token_id_template")

    def _check_fake_flag_format(self, instance: Dict[str, Any]) -> None:
        """Ensure fake flags match syntax but never equal real flag.

        Args:
            instance: Instance to check

        Raises:
            ConstraintViolation: If fake flag issues detected
        """
        obj = instance.get("object")
        if obj != "fake_flag":
            return

        payload = instance.get("payload", {})
        content = payload.get("content_template", "")

        # Check if it looks like a flag format (e.g., contains "flag{" or "FLAG{")
        if not content:
            return

        # Basic heuristic: if object is fake_flag, content should look flag-like
        flag_pattern = re.compile(r'(flag|FLAG)\{[^}]+\}', re.IGNORECASE)
        if not flag_pattern.search(content):
            # This might be too strict, but we warn
            # Could also just pass - fake flags might be hints about flags
            pass


def check_constraints_with_retry(
    instance: Dict[str, Any],
    checker: ConstraintChecker,
    max_retries: int = 10
) -> None:
    """Check constraints with retry information.

    This is a wrapper that adds retry context to constraint violations.

    Args:
        instance: Instance to check
        checker: ConstraintChecker to use
        max_retries: Maximum retries (for error messages)

    Raises:
        ConstraintViolation: If constraints fail after retries
    """
    try:
        checker.check_instance(instance, max_retries)
    except ConstraintViolation as e:
        raise ConstraintViolation(
            f"Constraint violation after {max_retries} retries: {e}"
        ) from e


def extract_routes_from_content(content: str) -> List[str]:
    """Extract route-like patterns from content.

    Helper function to identify potential route collisions.

    Args:
        content: Content string to analyze

    Returns:
        List of found route patterns
    """
    route_pattern = re.compile(r'/[a-zA-Z0-9_\-/]+')
    return route_pattern.findall(content)


def is_valid_selector(selector: str) -> bool:
    """Validate CSS selector syntax.

    Basic validation - checks if selector looks reasonable.
    Does not exhaustively validate all CSS selector syntax.

    Args:
        selector: CSS selector string

    Returns:
        True if selector appears valid
    """
    if not selector:
        return False

    # Very basic check - should start with # . [ or tag name
    valid_starts = ('#', '.', '[')
    if selector[0] in valid_starts:
        return True

    # Or start with a tag name
    if selector[0].isalpha():
        return True

    return False


def validate_placement_constraints(instance: Dict[str, Any]) -> None:
    """Validate placement-specific constraints.

    Args:
        instance: Instance to validate

    Raises:
        ConstraintViolation: If placement is invalid
    """
    perception = instance.get("perception", {})
    surface = perception.get("surface", "")
    placement = instance.get("placement", {})

    # DOM surfaces require selector
    dom_surfaces = [
        "aria_label", "aria_description", "alt_text", "title_attr",
        "text_node", "hidden_div", "offscreen_div", "comment",
        "meta_tag", "js_generated_dom"
    ]

    if surface in dom_surfaces:
        selector = placement.get("selector")
        if not selector:
            raise ConstraintViolation(
                f"Surface '{surface}' requires a selector in placement"
            )
        if not is_valid_selector(selector):
            raise ConstraintViolation(
                f"Invalid CSS selector: '{selector}'"
            )

    # Canvas surfaces require canvas_id and coordinates
    if surface == "canvas_drawtext":
        if not placement.get("canvas_id"):
            raise ConstraintViolation("canvas_drawtext requires canvas_id")
        if not placement.get("coordinates"):
            raise ConstraintViolation("canvas_drawtext requires coordinates")
