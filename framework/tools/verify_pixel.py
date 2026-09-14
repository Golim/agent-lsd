#!/usr/bin/env python3

"""Pixel verifier for deception instances.

Verifies that pixel-based deceptions cause visual changes via screenshot comparison.
Also checks that hidden DOM deceptions don't cause visual leakage.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from verifier_lib import (
    load_instance,
    get_instance_route,
    setup_browser,
    create_page,
    navigate_with_instance,
    WorkerPool,
    write_jsonl,
)


def compute_image_diff(img1: Image.Image, img2: Image.Image) -> float:
    """Compute mean absolute difference between two images.

    Args:
        img1: First image
        img2: Second image

    Returns:
        Mean absolute difference (MAD) over RGB channels
    """
    # Ensure same size
    if img1.size != img2.size:
        # Resize to match
        img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

    # Convert to numpy arrays
    arr1 = np.array(img1, dtype=np.float32)
    arr2 = np.array(img2, dtype=np.float32)

    # Compute MAD
    diff = np.abs(arr1 - arr2)
    mad = np.mean(diff)

    return float(mad)


async def capture_screenshots(
    base_url: str,
    route: str,
    instance_id: Optional[str],
    instance_mode: str,
    timeout_ms: int,
    wait_extra_ms: int,
    canvas_id: Optional[str] = None,
) -> Tuple[Optional[bytes], Optional[bytes]]:
    """Capture screenshots (fullpage and optionally element).

    Args:
        base_url: Base URL
        route: Route to visit
        instance_id: Instance ID (None for baseline)
        instance_mode: Instance activation mode
        timeout_ms: Navigation timeout
        wait_extra_ms: Extra wait time
        canvas_id: Optional canvas element ID for element screenshot

    Returns:
        Tuple of (fullpage_screenshot_bytes, element_screenshot_bytes)
    """
    browser, playwright = await setup_browser()

    try:
        page = await create_page(browser)

        success = await navigate_with_instance(
            page, base_url, route, instance_id, instance_mode, timeout_ms, wait_extra_ms
        )

        if not success:
            await browser.close()
            await playwright.stop()
            return None, None

        # Capture fullpage screenshot
        fullpage_bytes = await page.screenshot(full_page=True, type="png")

        # Capture element screenshot if canvas_id specified
        element_bytes = None
        if canvas_id:
            try:
                # Try to find element by ID
                element = await page.query_selector(f"#{canvas_id}")
                if element:
                    element_bytes = await element.screenshot(type="png")
                else:
                    # Try as general selector
                    element = await page.query_selector(canvas_id)
                    if element:
                        element_bytes = await element.screenshot(type="png")
            except Exception:
                pass

        await browser.close()
        await playwright.stop()

        return fullpage_bytes, element_bytes

    except Exception as e:
        try:
            await browser.close()
            await playwright.stop()
        except:
            pass
        return None, None


async def verify_pixel_instance(
    instance_path: Path,
    base_url: str,
    routes: List[str],
    instance_mode: str,
    timeout_ms: int,
    wait_extra_ms: int,
    threshold: float,
    threshold_small: float,
    element_threshold: float,
    screenshots_dir: Optional[Path],
) -> Dict[str, Any]:
    """Verify a single pixel instance.

    Args:
        instance_path: Path to instance file
        base_url: Base URL for testing
        routes: Default routes
        instance_mode: Instance activation mode
        timeout_ms: Navigation timeout
        wait_extra_ms: Extra wait time
        threshold: Fullpage diff threshold for pixel deceptions
        threshold_small: Threshold for hidden DOM (should be small)
        element_threshold: Element-specific diff threshold
        screenshots_dir: Optional directory to save screenshots

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

    # Determine routes to test
    test_routes = get_instance_route(instance, routes)
    route = test_routes[0]

    # Get canvas_id if specified
    placement = instance.get("placement", {})
    canvas_id = placement.get("canvas_id")

    result = {
        "instance_id": instance_id,
        "primitive_id": primitive_id,
        "route": route,
        "channel": channel,
        "surface": surface,
        "diff_fullpage": 0.0,
        "diff_element": None,
        "pixel_expected": False,
        "pixel_confirmed": False,
        "visual_leakage": False,
        "baseline_saved": False,
        "deception_saved": False,
        "errors": [],
        "pass": False,
    }

    try:
        # Determine expectations
        # if not channel.startswith("pixel."):
        #     # print(f"  [!] Skipping non-pixel channel instance: {instance_id} (channel={channel})")
        #     return result
        is_pixel_channel = channel.startswith("pixel.")
        is_hidden_dom = channel in ["dom.hidden", "dom.a11y", "dom.metadata"]

        result["pixel_expected"] = is_pixel_channel

        # Capture baseline (no instance)
        baseline_full, baseline_elem = await capture_screenshots(
            base_url, route, None, instance_mode, timeout_ms, wait_extra_ms, canvas_id
        )

        if baseline_full is None:
            result["errors"].append("Failed to capture baseline screenshot")
            return result

        # Capture with deception active
        deception_full, deception_elem = await capture_screenshots(
            base_url, route, instance_id, instance_mode, timeout_ms, wait_extra_ms, canvas_id
        )

        if deception_full is None:
            result["errors"].append("Failed to capture deception screenshot")
            return result

        # Save screenshots if requested
        if screenshots_dir:
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            baseline_path = screenshots_dir / f"{instance_id}_baseline.png"
            deception_path = screenshots_dir / f"{instance_id}_deception.png"

            with open(baseline_path, "wb") as f:
                f.write(baseline_full)
            result["baseline_saved"] = True

            with open(deception_path, "wb") as f:
                f.write(deception_full)
            result["deception_saved"] = True

        # Compute diffs
        baseline_img = Image.open(BytesIO(baseline_full))
        deception_img = Image.open(BytesIO(deception_full))

        result["diff_fullpage"] = compute_image_diff(baseline_img, deception_img)

        # Compute element diff if available
        if baseline_elem and deception_elem:
            baseline_elem_img = Image.open(BytesIO(baseline_elem))
            deception_elem_img = Image.open(BytesIO(deception_elem))
            result["diff_element"] = compute_image_diff(baseline_elem_img, deception_elem_img)

        # Determine if pixel changes confirmed
        # Use element diff if available, otherwise fullpage
        effective_diff = result["diff_element"] if result["diff_element"] is not None else result["diff_fullpage"]
        effective_threshold = element_threshold if result["diff_element"] is not None else threshold

        result["pixel_confirmed"] = effective_diff > effective_threshold

        # Check for visual leakage (hidden DOM shouldn't change pixels)
        if is_hidden_dom and result["diff_fullpage"] > threshold_small:
            result["visual_leakage"] = True
            result["errors"].append(f"Hidden DOM deception caused visual changes (diff={result['diff_fullpage']:.2f})")

        # Determine pass/fail
        if is_pixel_channel:
            # Pixel deceptions should cause visual changes
            if not result["pixel_confirmed"]:
                result["errors"].append(
                    f"Pixel deception did not cause sufficient visual changes "
                    f"(diff={effective_diff:.2f}, threshold={effective_threshold})"
                )
                result["pass"] = False
            else:
                result["pass"] = True

        elif is_hidden_dom:
            # Hidden DOM should not cause visual changes
            if result["visual_leakage"]:
                result["pass"] = False
            else:
                result["pass"] = True

        else:
            # Other channels (dom.visible, hybrid) - no strict requirement
            result["pass"] = True

    except Exception as e:
        result["errors"].append(f"Exception: {str(e)}")
        result["pass"] = False

    return result


# Import BytesIO
from io import BytesIO


async def verify_all_instances(
    instances_dir: Path,
    base_url: str,
    routes: List[str],
    instance_mode: str,
    timeout_ms: int,
    wait_extra_ms: int,
    threshold: float,
    threshold_small: float,
    element_threshold: float,
    workers: int,
    limit: Optional[int],
    output_path: Path,
    screenshots_dir: Optional[Path],
) -> List[Dict[str, Any]]:
    """Verify all instances.

    Args:
        instances_dir: Directory containing instances
        base_url: Base URL
        routes: Default routes
        instance_mode: Instance activation mode
        timeout_ms: Navigation timeout
        wait_extra_ms: Extra wait time
        threshold: Fullpage diff threshold
        threshold_small: Small diff threshold for hidden DOM
        element_threshold: Element diff threshold
        workers: Number of concurrent workers
        limit: Maximum instances to test
        output_path: Output JSONL path
        screenshots_dir: Optional screenshots directory

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
            verify_pixel_instance(
                instance_file,
                base_url,
                routes,
                instance_mode,
                timeout_ms,
                wait_extra_ms,
                threshold,
                threshold_small,
                element_threshold,
                screenshots_dir,
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
        diff_str = f"diff={result['diff_fullpage']:.2f}"
        print(f"  [{i}/{len(tasks)}] {status} {result['instance_id']} ({diff_str})")

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
        description="Verify pixel deceptions in generated instances"
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
        "--threshold",
        type=float,
        default=2.0,
        help="Fullpage MAD threshold for pixel deceptions (default: 2.0)",
    )
    parser.add_argument(
        "--threshold-small",
        type=float,
        default=0.5,
        help="Threshold for hidden DOM visual leakage detection (default: 0.5)",
    )
    parser.add_argument(
        "--element-threshold",
        type=float,
        default=1.0,
        help="Element-specific MAD threshold (default: 1.0)",
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
        default=Path("verification/pixel_results.jsonl"),
        help="Output JSONL file (default: verification/pixel_results.jsonl)",
    )
    parser.add_argument(
        "--screenshots-dir",
        type=Path,
        help="Optional directory to save screenshots",
    )
    parser.add_argument(
        "--soft-fail",
        action="store_true",
        help="Exit with code 0 even if instances fail",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail hard on visual leakage from hidden DOM",
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
                args.threshold,
                args.threshold_small,
                args.element_threshold,
                args.workers,
                args.limit,
                args.output,
                args.screenshots_dir,
            )
        )

        # Summary
        total = len(results)
        passed = sum(1 for r in results if r["pass"])
        failed = total - passed
        leakage_count = sum(1 for r in results if r.get("visual_leakage", False))

        # Compute average diffs by channel
        channel_diffs = {}
        for r in results:
            channel = r.get("channel", "unknown")
            if channel not in channel_diffs:
                channel_diffs[channel] = []
            channel_diffs[channel].append(r["diff_fullpage"])

        print(f"\n{'='*60}")
        print(f"Pixel Verification Summary")
        print(f"{'='*60}")
        print(f"Total:  {total}")
        print(f"Passed: {passed} ({100*passed/total:.1f}%)" if total > 0 else "Passed: 0")
        print(f"Failed: {failed}")
        print(f"Visual leakage detected: {leakage_count}")

        print(f"\nAverage diffs by channel:")
        for channel, diffs in sorted(channel_diffs.items()):
            avg_diff = sum(diffs) / len(diffs) if diffs else 0
            print(f"  {channel}: {avg_diff:.2f} MAD (n={len(diffs)})")

        print(f"\nResults written to: {args.output}")

        # Exit code
        if failed > 0 and not args.soft_fail:
            return 1

        if args.strict and leakage_count > 0:
            return 1

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
