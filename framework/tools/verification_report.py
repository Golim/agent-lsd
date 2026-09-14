#!/usr/bin/env python3

"""Merge and summarize verification results from DOM and pixel verifiers."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from verifier_lib import load_jsonl, write_jsonl


def merge_results(
    dom_results: List[Dict[str, Any]],
    pixel_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge DOM and pixel results by instance_id.

    Args:
        dom_results: List of DOM verification results
        pixel_results: List of pixel verification results

    Returns:
        List of merged results
    """
    # Index by instance_id + route
    dom_by_key = {}
    for r in dom_results:
        key = (r["instance_id"], r["route"])
        dom_by_key[key] = r

    pixel_by_key = {}
    for r in pixel_results:
        key = (r["instance_id"], r["route"])
        pixel_by_key[key] = r

    # Merge
    merged = []
    all_keys = set(dom_by_key.keys()) | set(pixel_by_key.keys())

    for key in sorted(all_keys):
        instance_id, route = key
        dom = dom_by_key.get(key)
        pixel = pixel_by_key.get(key)

        # Get common fields
        if dom:
            channel = dom.get("channel", "")
            surface = dom.get("surface", "")
            primitive_id = dom.get("primitive_id")
        elif pixel:
            channel = pixel.get("channel", "")
            surface = pixel.get("surface", "")
            primitive_id = pixel.get("primitive_id")
        else:
            channel = ""
            surface = ""
            primitive_id = None

        # Merge errors
        errors = []
        if dom:
            errors.extend(dom.get("errors", []))
        if pixel:
            errors.extend(pixel.get("errors", []))

        # Determine overall pass
        dom_pass = dom.get("pass") if dom else None
        pixel_pass = pixel.get("pass") if pixel else None

        # Overall pass: both must pass (if present)
        overall_pass = True
        if dom_pass is not None:
            overall_pass = overall_pass and dom_pass
        if pixel_pass is not None:
            overall_pass = overall_pass and pixel_pass

        result = {
            "instance_id": instance_id,
            "primitive_id": primitive_id,
            "route": route,
            "channel": channel,
            "surface": surface,
            "dom_pass": dom_pass,
            "pixel_pass": pixel_pass,
            "overall_pass": overall_pass,
            "errors": errors,
        }

        merged.append(result)

    return merged


def compute_summary(
    dom_results: List[Dict[str, Any]],
    pixel_results: List[Dict[str, Any]],
    merged_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute summary statistics.

    Args:
        dom_results: DOM results
        pixel_results: Pixel results
        merged_results: Merged results

    Returns:
        Summary dictionary
    """
    summary = {
        "total_instances": len(merged_results),
        "dom": {},
        "pixel": {},
        "merged": {},
        "by_channel": {},
        "by_surface": {},
    }

    # DOM summary
    if dom_results:
        dom_total = len(dom_results)
        dom_passed = sum(1 for r in dom_results if r.get("pass"))
        dom_failed = dom_total - dom_passed
        dom_leakage = sum(1 for r in dom_results if r.get("dom_leakage"))
        dom_selector_missing = sum(1 for r in dom_results if r.get("selector_missing"))

        summary["dom"] = {
            "total": dom_total,
            "passed": dom_passed,
            "failed": dom_failed,
            "pass_rate": f"{100*dom_passed/dom_total:.1f}%" if dom_total > 0 else "N/A",
            "dom_leakage_count": dom_leakage,
            "selector_missing_count": dom_selector_missing,
        }

    # Pixel summary
    if pixel_results:
        pixel_total = len(pixel_results)
        pixel_passed = sum(1 for r in pixel_results if r.get("pass"))
        pixel_failed = pixel_total - pixel_passed
        visual_leakage = sum(1 for r in pixel_results if r.get("visual_leakage"))

        # Average diffs
        avg_diff_fullpage = sum(r["diff_fullpage"] for r in pixel_results) / pixel_total if pixel_total > 0 else 0

        summary["pixel"] = {
            "total": pixel_total,
            "passed": pixel_passed,
            "failed": pixel_failed,
            "pass_rate": f"{100*pixel_passed/pixel_total:.1f}%" if pixel_total > 0 else "N/A",
            "visual_leakage_count": visual_leakage,
            "avg_diff_fullpage": f"{avg_diff_fullpage:.2f}",
        }

    # Merged summary
    if merged_results:
        merged_total = len(merged_results)
        merged_passed = sum(1 for r in merged_results if r.get("overall_pass"))
        merged_failed = merged_total - merged_passed

        summary["merged"] = {
            "total": merged_total,
            "passed": merged_passed,
            "failed": merged_failed,
            "pass_rate": f"{100*merged_passed/merged_total:.1f}%" if merged_total > 0 else "N/A",
        }

    # By channel
    channel_stats = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})
    for r in merged_results:
        channel = r.get("channel", "unknown")
        channel_stats[channel]["total"] += 1
        if r.get("overall_pass"):
            channel_stats[channel]["passed"] += 1
        else:
            channel_stats[channel]["failed"] += 1

    summary["by_channel"] = dict(channel_stats)

    # By surface
    surface_stats = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})
    for r in merged_results:
        surface = r.get("surface", "unknown")
        surface_stats[surface]["total"] += 1
        if r.get("overall_pass"):
            surface_stats[surface]["passed"] += 1
        else:
            surface_stats[surface]["failed"] += 1

    summary["by_surface"] = dict(surface_stats)

    # Average diffs by channel for pixel results
    if pixel_results:
        channel_diffs = defaultdict(list)
        for r in pixel_results:
            channel = r.get("channel", "unknown")
            channel_diffs[channel].append(r["diff_fullpage"])

        summary["pixel"]["avg_diff_by_channel"] = {
            channel: f"{sum(diffs)/len(diffs):.2f}"
            for channel, diffs in channel_diffs.items()
        }

    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    """Print summary to console.

    Args:
        summary: Summary dictionary
    """
    print(f"\n{'='*70}")
    print(f"Verification Summary")
    print(f"{'='*70}")

    print(f"\nTotal instances: {summary['total_instances']}")

    # DOM summary
    if summary.get("dom"):
        dom = summary["dom"]
        print(f"\nDOM Verification:")
        print(f"  Total:    {dom['total']}")
        print(f"  Passed:   {dom['passed']} ({dom['pass_rate']})")
        print(f"  Failed:   {dom['failed']}")
        print(f"  DOM leakage (pixel→DOM): {dom['dom_leakage_count']}")
        print(f"  Selector missing: {dom['selector_missing_count']}")

    # Pixel summary
    if summary.get("pixel"):
        pixel = summary["pixel"]
        print(f"\nPixel Verification:")
        print(f"  Total:    {pixel['total']}")
        print(f"  Passed:   {pixel['passed']} ({pixel['pass_rate']})")
        print(f"  Failed:   {pixel['failed']}")
        print(f"  Visual leakage (hidden DOM→pixel): {pixel['visual_leakage_count']}")
        print(f"  Avg fullpage diff: {pixel['avg_diff_fullpage']} MAD")

        if "avg_diff_by_channel" in pixel:
            print(f"\n  Avg diff by channel:")
            for channel, avg in sorted(pixel["avg_diff_by_channel"].items()):
                print(f"    {channel}: {avg} MAD")

    # Merged summary
    if summary.get("merged"):
        merged = summary["merged"]
        print(f"\nOverall (Merged):")
        print(f"  Total:    {merged['total']}")
        print(f"  Passed:   {merged['passed']} ({merged['pass_rate']})")
        print(f"  Failed:   {merged['failed']}")

    # By channel
    if summary.get("by_channel"):
        print(f"\nBy Channel:")
        for channel, stats in sorted(summary["by_channel"].items()):
            pass_rate = f"{100*stats['passed']/stats['total']:.1f}%" if stats['total'] > 0 else "N/A"
            print(f"  {channel:20s}: {stats['passed']}/{stats['total']} passed ({pass_rate})")

    # By surface
    if summary.get("by_surface"):
        print(f"\nBy Surface:")
        for surface, stats in sorted(summary["by_surface"].items()):
            pass_rate = f"{100*stats['passed']/stats['total']:.1f}%" if stats['total'] > 0 else "N/A"
            print(f"  {surface:20s}: {stats['passed']}/{stats['total']} passed ({pass_rate})")

    print(f"\n{'='*70}")


def main(argv: List[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command line arguments

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Merge and summarize verification results"
    )
    parser.add_argument(
        "--dom-results",
        type=Path,
        default=Path("verification/dom_results.jsonl"),
        help="DOM verification results JSONL",
    )
    parser.add_argument(
        "--pixel-results",
        type=Path,
        default=Path("verification/pixel_results.jsonl"),
        help="Pixel verification results JSONL",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("verification/merged.jsonl"),
        help="Output merged results JSONL",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional JSON file for summary statistics",
    )

    args = parser.parse_args(argv)

    try:
        # Load results
        dom_results = load_jsonl(args.dom_results) if args.dom_results.exists() else []
        pixel_results = load_jsonl(args.pixel_results) if args.pixel_results.exists() else []

        if not dom_results and not pixel_results:
            print("Error: No results found to merge", file=sys.stderr)
            return 1

        # Merge
        merged_results = merge_results(dom_results, pixel_results)

        # Write merged results
        write_jsonl(args.output, merged_results)
        print(f"Merged results written to: {args.output}")

        # Compute summary
        summary = compute_summary(dom_results, pixel_results, merged_results)

        # Write summary JSON if requested
        if args.summary_json:
            args.summary_json.parent.mkdir(parents=True, exist_ok=True)
            with open(args.summary_json, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, sort_keys=True)
            print(f"Summary JSON written to: {args.summary_json}")

        # Print summary
        print_summary(summary)

        # Exit code based on pass rate
        if summary.get("merged"):
            if summary["merged"]["failed"] > 0:
                return 1

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
