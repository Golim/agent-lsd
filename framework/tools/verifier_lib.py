#!/usr/bin/env python3

"""Shared utilities for DOM and pixel verification."""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from playwright.async_api import async_playwright, Page, Browser


def load_instance(instance_path: Path) -> Dict[str, Any]:
    """Load a resolved instance YAML file.

    Args:
        instance_path: Path to .resolved.yaml file

    Returns:
        Instance dictionary
    """
    with open(instance_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Args:
        text: Input text

    Returns:
        Normalized text (collapsed whitespace, lowercased)
    """
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def extract_key_substring(text: str, min_len: int = 40, max_len: int = 80) -> str:
    """Extract a key substring for robust searching.

    Args:
        text: Input text
        min_len: Minimum length
        max_len: Maximum length

    Returns:
        Alphanumeric-only substring
    """
    # Extract alphanumeric only
    alnum = re.sub(r'[^a-zA-Z0-9]+', '', text)

    # Take first min_len to max_len chars
    if len(alnum) < min_len:
        return alnum.lower()

    return alnum[:max_len].lower()


def get_instance_route(instance: Dict[str, Any], default_routes: List[str]) -> List[str]:
    """Get routes to test for an instance.

    Args:
        instance: Instance dictionary
        default_routes: Default routes if not specified

    Returns:
        List of routes to test
    """
    placement = instance.get("placement", {})
    route = placement.get("route")

    if route:
        # Clean up route
        if not route.startswith("/"):
            route = "/" + route
        return [route]

    return default_routes


def get_payload_content(instance: Dict[str, Any]) -> str:
    """Extract rendered payload content from instance.

    Args:
        instance: Instance dictionary

    Returns:
        Payload content string
    """
    payload = instance.get("payload", {})
    return payload.get("content_template", "")


async def setup_browser(viewport_width: int = 1280, viewport_height: int = 720) -> tuple[Browser, Any]:
    """Setup Playwright browser with deterministic settings.

    Args:
        viewport_width: Viewport width
        viewport_height: Viewport height

    Returns:
        Tuple of (browser, playwright instance)
    """
    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--no-sandbox',
        ]
    )

    return browser, playwright


async def create_page(browser: Browser, viewport_width: int = 1280, viewport_height: int = 720) -> Page:
    """Create a new page with deterministic settings.

    Args:
        browser: Browser instance
        viewport_width: Viewport width
        viewport_height: Viewport height

    Returns:
        Page instance
    """
    context = await browser.new_context(
        viewport={"width": viewport_width, "height": viewport_height},
        reduced_motion="reduce",  # Disable animations
        locale="en-US",
        timezone_id="America/New_York",
    )

    page = await context.new_page()

    # Disable image loading for faster rendering (optional, can enable if needed)
    # await context.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())

    return page


async def navigate_with_instance(
    page: Page,
    base_url: str,
    route: str,
    instance_id: Optional[str] = None,
    instance_mode: str = "header",
    timeout_ms: int = 30000,
    wait_extra_ms: int = 250
) -> bool:
    """Navigate to a route with optional instance activation.

    Args:
        page: Playwright page
        base_url: Base URL
        route: Route to visit
        instance_id: Instance ID (None for baseline)
        instance_mode: "header", "query", or "both"
        timeout_ms: Navigation timeout
        wait_extra_ms: Extra wait after network idle

    Returns:
        True if successful, False on error
    """
    url = base_url.rstrip("/") + route

    # Add query parameter if needed
    if instance_id and instance_mode in ("query", "both"):
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}instance={instance_id}"

    try:
        # IMPORTANT: avoid setting the instance header globally on the page.
        # Global headers also affect cross-origin CSS/JS/font requests and can
        # break CORS/SRI loading, producing false visual diffs.
        use_header = bool(instance_id and instance_mode in ("header", "both"))
        route_handler = None

        if use_header:
            target_parts = urlsplit(url)
            target_no_query = urlunsplit((target_parts.scheme, target_parts.netloc, target_parts.path, "", ""))

            async def route_handler(route):
                request = route.request
                request_parts = urlsplit(request.url)
                request_no_query = urlunsplit((request_parts.scheme, request_parts.netloc, request_parts.path, "", ""))

                is_main_document = (
                    request.resource_type == "document"
                    and request.frame == page.main_frame
                    and request_no_query == target_no_query
                )

                if is_main_document:
                    headers = dict(request.headers)
                    headers["X-Instance-Id"] = instance_id
                    await route.continue_(headers=headers)
                else:
                    await route.continue_()

            await page.route("**/*", route_handler)

        await page.goto(url, wait_until="networkidle", timeout=timeout_ms)

        # Ensure late style/font/layout work has settled before capture.
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        await page.evaluate(
            """
            async () => {
                if (document.fonts && document.fonts.status !== 'loaded') {
                    await document.fonts.ready;
                }
                await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            }
            """
        )

        # Extra wait for any animations/rendering
        if wait_extra_ms > 0:
            await asyncio.sleep(wait_extra_ms / 1000.0)

        if use_header and route_handler is not None:
            await page.unroute("**/*", route_handler)

        return True

    except Exception as e:
        try:
            if instance_id and instance_mode in ("header", "both") and route_handler is not None:
                await page.unroute("**/*", route_handler)
        except Exception:
            pass
        return False


async def get_dom_snapshot(page: Page) -> Dict[str, Any]:
    """Get comprehensive DOM snapshot.

    Args:
        page: Playwright page

    Returns:
        Dictionary with html, visible_text, and a11y_snapshot
    """
    result = {
        "html": "",
        "visible_text": "",
        "a11y_snapshot": None,
        "a11y_string": ""
    }

    try:
        result["html"] = await page.content()
    except Exception:
        pass

    try:
        result["visible_text"] = await page.inner_text("body")
    except Exception:
        pass

    try:
        result["a11y_snapshot"] = await page.accessibility.snapshot()
        # Convert to searchable string
        if result["a11y_snapshot"]:
            result["a11y_string"] = json.dumps(result["a11y_snapshot"]).lower()
    except Exception:
        pass

    return result


def check_selector_exists(html: str, selector: str) -> bool:
    """Basic check if selector might exist in HTML.

    This is a simple heuristic since we can't run full CSS selector matching
    on raw HTML. Checks for ID, class, or tag name patterns.

    Args:
        html: HTML content
        selector: CSS selector

    Returns:
        True if selector pattern found
    """
    html_lower = html.lower()
    selector_lower = selector.lower()

    # Check for ID selector
    if selector.startswith("#"):
        id_value = selector[1:].split("[")[0].split(":")[0]
        if f'id="{id_value}"' in html_lower or f"id='{id_value}'" in html_lower:
            return True

    # Check for class selector
    if selector.startswith("."):
        class_value = selector[1:].split("[")[0].split(":")[0]
        if f'class="{class_value}"' in html_lower or f"class='{class_value}'" in html_lower:
            return True
        # Also check for class in class list
        if class_value in html_lower:
            return True

    # Check for tag name
    if selector and selector[0].isalpha():
        tag_name = selector.split("[")[0].split(".")[0].split("#")[0].split(":")[0]
        if f"<{tag_name}" in html_lower or f"<{tag_name.upper()}" in html:
            return True

    # If none of the above, assume it might exist (conservative)
    return True


async def check_selector_playwright(page: Page, selector: str) -> bool:
    """Check if selector exists using Playwright.

    Args:
        page: Playwright page
        selector: CSS selector

    Returns:
        True if at least one element matches
    """
    try:
        elements = await page.query_selector_all(selector)
        return len(elements) > 0
    except Exception:
        return False


class WorkerPool:
    """Async worker pool with semaphore."""

    def __init__(self, max_workers: int):
        """Initialize worker pool.

        Args:
            max_workers: Maximum concurrent workers
        """
        self.semaphore = asyncio.Semaphore(max_workers)

    async def run(self, coro):
        """Run a coroutine with semaphore.

        Args:
            coro: Coroutine to run

        Returns:
            Result of coroutine
        """
        async with self.semaphore:
            return await coro


def write_jsonl(output_path: Path, results: List[Dict[str, Any]]) -> None:
    """Write results to JSONL file.

    Args:
        output_path: Output file path
        results: List of result dictionaries
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, sort_keys=True) + "\n")


def load_jsonl(input_path: Path) -> List[Dict[str, Any]]:
    """Load results from JSONL file.

    Args:
        input_path: Input file path

    Returns:
        List of result dictionaries
    """
    results = []

    if not input_path.exists():
        return results

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))

    return results
