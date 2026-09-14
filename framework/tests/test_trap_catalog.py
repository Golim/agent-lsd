"""Tests for endpoint trap catalog classification."""

from __future__ import annotations

import json

from deception_runtime.trap_catalog import EndpointTrapClassifier


def test_exact_endpoint_classification() -> None:
    classifier = EndpointTrapClassifier()
    classification = classifier.classify("/console")

    assert classification.trap_type == "admin_console"
    assert classification.catalog_match_type == "exact"


def test_pattern_endpoint_classification() -> None:
    classifier = EndpointTrapClassifier()
    classification = classifier.classify("/45dfddb2")

    assert classification.trap_type == "opaque_internal"
    assert classification.catalog_match_type == "pattern"


def test_fallback_classification() -> None:
    classifier = EndpointTrapClassifier()
    classification = classifier.classify("/unmapped/endpoint/path")

    assert classification.trap_type == "hidden_index"
    assert classification.catalog_match_type == "fallback"


def test_deterministic_template_selection() -> None:
    classifier = EndpointTrapClassifier()

    first = classifier.classify("/panel/api_v1/backup")
    second = classifier.classify("/panel/api_v1/backup")

    assert first.template_name == second.template_name
    assert first.trap_type == second.trap_type


def test_explicit_map_file_override(tmp_path) -> None:
    mapping_file = tmp_path / "endpoint_map.json"
    mapping_file.write_text(
        json.dumps({"/status": "admin_console"}),
        encoding="utf-8",
    )

    classifier = EndpointTrapClassifier(map_file_path=str(mapping_file))
    classification = classifier.classify("/status")

    assert classification.trap_type == "admin_console"
    assert classification.catalog_match_type == "explicit"
