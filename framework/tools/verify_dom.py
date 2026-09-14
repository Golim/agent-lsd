#!/usr/bin/env python3

"""DOM verifier for deception instances.

Verifies that DOM-based deceptions are detectable in HTML, visible text, or accessibility tree.
Also checks that pixel-only deceptions don't leak to DOM.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from verifier_lib import (
    load_instance,
    normalize_text,
    extract_key_substring,
    get_instance_route,
    get_payload_content,
    setup_browser,
    create_page,
    navigate_with_instance,
    get_dom_snapshot,
    check_selector_playwright,
    WorkerPool,
    write_jsonl,
)


async def verify_dom_instance(
    instance_path: Path,
    base_url: str,
    routes: List[str],
    instance_mode: str,
    timeout_ms: int,
    wait_extra_ms: int,
) -> Dict[str, Any]:
    """Verify a single DOM instance.

    Args:
        instance_path: Path to instance file
        base_url: Base URL for testing
        routes: Default routes
        instance_mode: Instance activation mode
        timeout_ms: Navigation timeout
        wait_extra_ms: Extra wait time

    Returns:
        Verification result dictionary
    """
    # Load instance
    instance = load_instance(instance_path)
    instance_id = instance.get("id", instance_path.stem)
    primitive_id = instance.get("_primitive_id")

    perception = instance.get("perception", {})
    channel = perception.get("channel", "")
    surface = perception.get("surface", "")
    human_visibility = instance.get("human_visibility", "human_subtle")

    # Get payload content
    payload_content = get_payload_content(instance)
    payload_normalized = normalize_text(payload_content)
    payload_key = extract_key_substring(payload_content)

    # Determine routes to test
    test_routes = get_instance_route(instance, routes)

    # Setup browser
    browser, playwright = await setup_browser()

    try:
        # Test first route (can extend to test all routes)
        route = test_routes[0]

        result = {
            "instance_id": instance_id,
            "primitive_id": primitive_id,
            "route": route,
            "channel": channel,
            "surface": surface,
            "human_visibility": human_visibility,
            "payload_length": len(payload_content),
            "dom_present": False,
            "dom_leakage": False,
            "selector_missing": False,
            "html_present": False,
            "visible_present": False,
            "a11y_present": False,
            "errors": [],
            "pass": False,
        }

        # Create page and navigate
        page = await create_page(browser)

        success = await navigate_with_instance(
            page, base_url, route, instance_id, instance_mode, timeout_ms, wait_extra_ms
        )

        if not success:
            result["errors"].append(f"Navigation failed to {route}")
            await browser.close()
            await playwright.stop()
            return result

        # Get DOM snapshot
        snapshot = await get_dom_snapshot(page)

        # Normalize all content for searching
        html_normalized = normalize_text(snapshot["html"])
        visible_normalized = normalize_text(snapshot["visible_text"])
        a11y_string = snapshot["a11y_string"]

        # Check if payload is present in DOM
        if payload_normalized and payload_key:
            # Check HTML
            if payload_normalized in html_normalized or payload_key in html_normalized:
                result["html_present"] = True

            # Check visible text (only if not human_hidden)
            if human_visibility != "human_hidden":
                if payload_normalized in visible_normalized or payload_key in visible_normalized:
                    result["visible_present"] = True

            # Check a11y snapshot
            if a11y_string:
                if payload_normalized in a11y_string or payload_key in a11y_string:
                    result["a11y_present"] = True

        # Determine if DOM present
        result["dom_present"] = (
            result["html_present"] or 
            result["visible_present"] or 
            result["a11y_present"]
        )

        # Check selector if DOM surface
        placement = instance.get("placement", {})
        selector = placement.get("selector")

        if channel.startswith("dom.") and selector:
            selector_exists = await check_selector_playwright(page, selector)
            if not selector_exists:
                result["selector_missing"] = True
                result["errors"].append(f"Selector not found: {selector}")

        # Determine pass/fail
        if channel.startswith("dom."):
            # DOM deceptions should be present
            if not result["dom_present"]:
                result["errors"].append("DOM deception not detected in HTML/visible/a11y")
                result["pass"] = False
            elif result["selector_missing"]:
                result["pass"] = False
            else:
                result["pass"] = True

        elif channel.startswith("pixel."):
            # Pixel deceptions should NOT leak to DOM
            if result["dom_present"] and payload_content:
                result["dom_leakage"] = True
                result["errors"].append("Pixel deception leaked to DOM")
                result["pass"] = False
            else:
                result["pass"] = True

        else:
            # Hybrid or other
            result["pass"] = True

        await browser.close()

    except Exception as e:
        result = {
            "instance_id": instance_id,
            "primitive_id": primitive_id,
            "route": test_routes[0] if test_routes else "/",
            "channel": channel,
            "surface": surface,
            "human_visibility": human_visibility,
            "payload_length": len(payload_content),
            "dom_present": False,
            "dom_leakage": False,
            "selector_missing": False,
            "html_present": False,
            "visible_present": False,
            "a11y_present": False,
            "errors": [f"Exception: {str(e)}"],
            "pass": False,
        }

        try:
            await browser.close()
        except:
            pass

    finally:
        try:
            await playwright.stop()
        except:
            pass

    return result


async def verify_all_instances(
    instances_dir: Path,
    base_url: str,
    routes: List[str],
    instance_mode: str,
    timeout_ms: int,
    wait_extra_ms: int,
    workers: int,
    limit: Optional[int],
    output_path: Path,
) -> List[Dict[str, Any]]:
    """Verify all instances.

    Args:
        instances_dir: Directory containing instances
        base_url: Base URL
        routes: Default routes
        instance_mode: Instance activation mode
        timeout_ms: Navigation timeout
        wait_extra_ms: Extra wait time
        workers: Number of concurrent workers
        limit: Maximum instances to test
        output_path: Output JSONL path

    Returns:
        List of results
    """
    # Find all resolved instance files
    instance_files = sorted(instances_dir.glob("*.resolved.yaml"))

    if limit:
        instance_files = instance_files[:limit]

    print(f"Found {len(instance_files)} instances to verify")

    # Create worker pool
    pool = WorkerPool(workers)

    # Create tasks
    tasks = []
    for instance_file in instance_files:
        task = pool.run(
            verify_dom_instance(
                instance_file,
                base_url,
                routes,
                instance_mode,
                timeout_ms,
                wait_extra_ms,
            )
        )
        tasks.append(task)

    # Run all tasks
    results = []
    for i, task in enumerate(asyncio.as_completed(tasks), 1):
        result = await task
        results.append(result)

        # Progress
        status = "✓" if result["pass"] else "✗"
        print(f"  [{i}/{len(tasks)}] {status} {result['instance_id']}")

        # Write incrementally
        write_jsonl(output_path, results)

    return results


def main(argv: List[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Verify DOM deceptions in generated instances"
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:5000",
        help="Base URL for web challenge (default: http://127.0.0.1:5000)",
    )
    parser.add_argument(
        "--instances-dir",
        type=Path,
        default=Path("deceptions/instances/generated"),
        help="Directory containing instance files",
    )
    parser.add_argument(
        "--routes",
        default="/,/login,/help",
        help="Comma-separated default routes (default: /,/login,/help)",
    )
    parser.add_argument(
        "--instance-mode",
        choices=["header", "query", "both"],
        default="header",
        help="Instance activation mode (default: header)",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30000,
        help="Navigation timeout in milliseconds (default: 30000)",
    )
    parser.add_argument(
        "--wait-extra-ms",
        type=int,
        default=250,
        help="Extra wait after network idle in ms (default: 250)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent workers (default: 4)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of instances to test",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("verification/dom_results.jsonl"),
        help="Output JSONL file (default: verification/dom_results.jsonl)",
    )
    parser.add_argument(
        "--soft-fail",
        action="store_true",
        help="Exit with code 0 even if instances fail",
    )

    args = parser.parse_args(argv)

    # Parse routes
    routes = [r.strip() for r in args.routes.split(",") if r.strip()]

    # Run verification
    try:
        results = asyncio.run(
            verify_all_instances(
                args.instances_dir,
                args.base_url,
                routes,
                args.instance_mode,
                args.timeout_ms,
                args.wait_extra_ms,
                args.workers,
                args.limit,
                args.output,
            )
        )

        # Summary
        total = len(results)
        passed = sum(1 for r in results if r["pass"])
        failed = total - passed

        print(f"\n{'='*60}")
        print(f"DOM Verification Summary")
        print(f"{'='*60}")
        print(f"Total:  {total}")
        print(f"Passed: {passed} ({100*passed/total:.1f}%)" if total > 0 else "Passed: 0")
        print(f"Failed: {failed}")
        print(f"\nResults written to: {args.output}")

        # Exit code
        if failed > 0 and not args.soft_fail:
            return 1

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
