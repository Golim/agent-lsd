#!/usr/bin/env python3

"""Manifest generation for deception instances.

Creates a JSONL manifest describing all generated instances.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, TextIO


def extract_manifest_entry(instance: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """Extract manifest entry from a generated instance.

    Args:
        instance: Generated instance dictionary
        seed: Seed used to generate this instance

    Returns:
        Manifest entry dictionary
    """
    perception = instance.get("perception", {})
    honeytoken = instance.get("honeytoken", {})

    entry = {
        "instance_id": instance.get("id", ""),
        "primitive_id": instance.get("_primitive_id", "unknown"),
        "intent": instance.get("intent", ""),
        "object": instance.get("object", ""),
        "perception": {
            "channel": perception.get("channel", ""),
            "surface": perception.get("surface", ""),
        },
        "human_visibility": instance.get("human_visibility", "human_subtle"),
        "plausibility": instance.get("plausibility", "medium"),
        "severity": instance.get("severity", "minor_delay"),
        "attribution_value": instance.get("attribution_value", "none"),
        "has_honeytoken": honeytoken.get("enabled", False),
        "seed": seed,
        "pair_group": instance.get("_pair_group"),  # Can be None
    }

    return entry


def write_manifest_entry(fileobj: TextIO, entry: Dict[str, Any]) -> None:
    """Write a single manifest entry as JSONL.

    Args:
        fileobj: File object to write to
        entry: Manifest entry dictionary
    """
    fileobj.write(json.dumps(entry, sort_keys=True) + "\n")


def create_manifest(
    instances: List[tuple[Dict[str, Any], int]],
    output_path: str
) -> None:
    """Create a complete manifest file.

    Args:
        instances: List of (instance_dict, seed) tuples
        output_path: Path to write manifest.jsonl
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for instance, seed in instances:
            entry = extract_manifest_entry(instance, seed)
            write_manifest_entry(f, entry)


def load_manifest(manifest_path: str) -> List[Dict[str, Any]]:
    """Load manifest from JSONL file.

    Args:
        manifest_path: Path to manifest.jsonl

    Returns:
        List of manifest entries
    """
    entries = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def get_paired_instances(manifest: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group manifest entries by pair_group.

    Args:
        manifest: List of manifest entries

    Returns:
        Dictionary mapping pair_group to list of entries
    """
    pairs = {}
    for entry in manifest:
        pair_group = entry.get("pair_group")
        if pair_group:
            if pair_group not in pairs:
                pairs[pair_group] = []
            pairs[pair_group].append(entry)
    return pairs


def summarize_manifest(manifest: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create summary statistics for a manifest.

    Args:
        manifest: List of manifest entries

    Returns:
        Summary statistics dictionary
    """
    total = len(manifest)

    # Count by intent
    by_intent = {}
    for entry in manifest:
        intent = entry.get("intent", "unknown")
        by_intent[intent] = by_intent.get(intent, 0) + 1

    # Count by channel
    by_channel = {}
    for entry in manifest:
        channel = entry.get("perception", {}).get("channel", "unknown")
        by_channel[channel] = by_channel.get(channel, 0) + 1

    # Count honeytokens
    with_honeytokens = sum(1 for e in manifest if e.get("has_honeytoken"))

    # Count paired instances
    pairs = get_paired_instances(manifest)
    num_pairs = len(pairs)

    return {
        "total_instances": total,
        "by_intent": by_intent,
        "by_channel": by_channel,
        "with_honeytokens": with_honeytokens,
        "num_pair_groups": num_pairs,
    }
