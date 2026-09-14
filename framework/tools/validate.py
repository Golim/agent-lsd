#!/usr/bin/env python3

"""Utility to validate a YAML instance against a JSON Schema.

This module is written to be used both as a library and a CLI tool.

Public functions
- ``load_json_schema(schema_path)``: load a JSON schema from a file path.
- ``load_yaml_instance(instance_path)``: load a YAML document from a file path.
- ``validate_instance(instance, schema)``: validate a Python object (parsed YAML)
  against a JSON Schema. Raises ``jsonschema.exceptions.ValidationError`` on
  validation failure.
- ``validate_files(schema_path, instance_path)``: convenience wrapper to load
  both files and validate them.

The module prefers the widely-used external packages ``PyYAML`` and
``jsonschema``. If they are not installed an ``ImportError`` will be raised
with an explanatory message.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

try:
	import yaml
except Exception as exc:  # pragma: no cover - runtime dependency
	raise ImportError(
		"PyYAML is required to load YAML instances. Install with 'pip install pyyaml'"
	) from exc

try:
	from jsonschema import Draft7Validator, exceptions as jsonschema_exceptions
except Exception as exc:  # pragma: no cover - runtime dependency
	raise ImportError(
		"jsonschema is required to perform validation. Install with 'pip install jsonschema'"
	) from exc

__all__ = [
	"load_json_schema",
	"load_yaml_instance",
	"validate_instance",
	"validate_files",
]


def load_json_schema(schema_path: str) -> Dict[str, Any]:
	"""Load a JSON Schema from a file.

	Parameters
	- schema_path: Path to a file containing a JSON schema.

	Returns
	- A dict representing the JSON schema.

	Raises
	- ``json.JSONDecodeError`` if the file is not valid JSON.
	- ``FileNotFoundError`` if the file does not exist.
	"""

	with open(schema_path, "r", encoding="utf-8") as fh:
		return json.load(fh)


def load_yaml_instance(instance_path: str) -> Any:
	"""Load a YAML document from a file and return the parsed Python object.

	Parameters
	- instance_path: Path to a YAML file.

	Returns
	- The Python object produced by ``yaml.safe_load``.

	Raises
	- ``yaml.YAMLError`` if the file is not valid YAML.
	- ``FileNotFoundError`` if the file does not exist.
	"""

	with open(instance_path, "r", encoding="utf-8") as fh:
		return yaml.safe_load(fh)


def validate_instance(instance: Any, schema: Dict[str, Any]) -> None:
	"""Validate ``instance`` against ``schema``.

	This function raises ``jsonschema.exceptions.ValidationError`` when the
	instance does not conform to the schema. If validation passes the
	function returns ``None``.

	Parameters
	- instance: The Python object to validate (typically produced by YAML load).
	- schema: The JSON Schema as a mapping.

	Raises
	- ``jsonschema.exceptions.ValidationError`` when validation fails. The
	  exception message will contain a summary of errors.
	"""

	validator = Draft7Validator(schema)
	errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
	if not errors:
		return

	# Format errors in a compact, useful form for both CLI and library users.
	lines = []
	for err in errors:
		path = "/".join(map(str, err.path)) or "<root>"
		lines.append(f"{path}: {err.message}")

	raise jsonschema_exceptions.ValidationError("\n".join(lines))


def validate_files(schema_path: str, instance_path: str) -> None:
	"""Convenience wrapper: load schema and instance from files and validate.

	Parameters
	- schema_path: path to JSON Schema file
	- instance_path: path to YAML instance file

	Raises
	- ``jsonschema.exceptions.ValidationError`` on validation failure
	- ``json.JSONDecodeError`` or ``yaml.YAMLError`` on malformed files
	"""

	schema = load_json_schema(schema_path)
	instance = load_yaml_instance(instance_path)
	validate_instance(instance, schema)


def _main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Validate a YAML instance against a JSON Schema")
	parser.add_argument("schema", help="Path to JSON Schema file (JSON)")
	parser.add_argument("instance", help="Path to instance file (YAML)")
	args = parser.parse_args(argv)

	try:
		validate_files(args.schema, args.instance)
	except jsonschema_exceptions.ValidationError as exc:
		print("Validation failed:")
		print(exc)
		return 2
	except Exception as exc:  # pragma: no cover - surface errors reported to user
		print("Error while validating:")
		print(repr(exc))
		return 3

	print("OK: instance conforms to schema")
	return 0


if __name__ == "__main__":
	raise SystemExit(_main())
