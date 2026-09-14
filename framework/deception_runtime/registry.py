"""
Deception instance registry: load and index resolved instances from disk.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise ImportError(
        "deception_runtime requires PyYAML. Install with: pip install pyyaml"
    ) from exc

from deception_runtime.logging import StructuredLogger

logger = StructuredLogger(__name__)


@dataclass
class DeceptionInstance:
    """
    A loaded deception instance with indexed access to key fields.
    """

    instance_id: str
    primitive_id: str | None
    channel: str
    surface: str
    payload_text: str
    placement: dict[str, Any]
    honeytoken: dict[str, Any] | None
    raw: dict[str, Any]

    @property
    def route(self) -> str | None:
        """Get route from placement if present."""
        return self.placement.get("route")

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_file: str) -> "DeceptionInstance":
        """
        Load a DeceptionInstance from resolved YAML dict.
        """
        instance_id = data.get("id")
        if not instance_id:
            raise ValueError(f"Missing 'id' in {source_file}")

        perception = data.get("perception", {})
        channel = perception.get("channel")
        surface = perception.get("surface")

        if not channel:
            raise ValueError(f"Missing 'perception.channel' in {source_file}")
        if not surface:
            raise ValueError(f"Missing 'perception.surface' in {source_file}")

        payload = data.get("payload", {})
        payload_text = payload.get("content_template", "")

        placement = data.get("placement", {})
        honeytoken = data.get("honeytoken")
        primitive_id = data.get("_primitive_id") or data.get("primitive_id")

        return cls(
            instance_id=instance_id,
            primitive_id=primitive_id,
            channel=channel,
            surface=surface,
            payload_text=payload_text,
            placement=placement,
            honeytoken=honeytoken,
            raw=data,
        )


class DeceptionRegistry:
    """
    Registry that loads and indexes deception instances from disk.
    """

    def __init__(
        self,
        instances_dir: str | Path,
        schema_path: str | Path | None = None,
        validate_schema: bool = True,
    ):
        self.instances_dir = Path(instances_dir)
        self.schema_path = Path(schema_path) if schema_path else None
        self.validate_schema = validate_schema

        self._instances: dict[str, DeceptionInstance] = {}
        self._by_route: dict[str, list[DeceptionInstance]] = {}
        self._schema: dict[str, Any] | None = None

        self._load_schema()
        self._load_instances()

    def _load_schema(self) -> None:
        """Load JSON schema if available."""
        if not self.validate_schema or not self.schema_path:
            return

        if not self.schema_path.exists():
            logger.warning(
                "Schema file not found, skipping validation",
                schema_path=str(self.schema_path),
            )
            return

        try:
            with open(self.schema_path) as f:
                self._schema = json.load(f)
            logger.info("Loaded schema", schema_path=str(self.schema_path))
        except Exception as e:
            logger.warning(
                "Failed to load schema, skipping validation",
                schema_path=str(self.schema_path),
                error=str(e),
            )

    def _validate_instance(self, data: dict[str, Any], source_file: str) -> None:
        """Validate instance against schema if available."""
        if not self._schema:
            return

        try:
            import jsonschema

            clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
            jsonschema.validate(instance=clean_data, schema=self._schema)
        except ImportError:
            pass
        except jsonschema.ValidationError as e:
            logger.warning(
                "Schema validation failed",
                source_file=source_file,
                error=str(e.message),
            )

    def _load_instances(self) -> None:
        """Load all *.resolved.yaml files from instances_dir."""
        if not self.instances_dir.exists():
            logger.warning(
                "Instances directory not found",
                instances_dir=str(self.instances_dir),
            )
            return

        if not self.instances_dir.is_dir():
            logger.error(
                "Instances path is not a directory",
                instances_dir=str(self.instances_dir),
            )
            return

        yaml_files = list(self.instances_dir.glob("*.resolved.yaml"))
        if not yaml_files:
            logger.warning(
                "No resolved instance files found",
                instances_dir=str(self.instances_dir),
            )
            return

        logger.info(
            "Loading instances",
            instances_dir=str(self.instances_dir),
            file_count=len(yaml_files),
        )

        loaded = 0
        failed = 0
        for yaml_file in yaml_files:
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if not data:
                    logger.warning("Empty YAML file", file=str(yaml_file))
                    failed += 1
                    continue

                self._validate_instance(data, str(yaml_file))
                instance = DeceptionInstance.from_dict(data, str(yaml_file))

                if instance.instance_id in self._instances:
                    logger.warning(
                        "Duplicate instance_id found, overwriting",
                        instance_id=instance.instance_id,
                        file=str(yaml_file),
                    )

                self._instances[instance.instance_id] = instance

                if instance.route:
                    self._by_route.setdefault(instance.route, []).append(instance)

                loaded += 1
            except Exception as e:
                logger.error(
                    "Failed to load instance",
                    file=str(yaml_file),
                    error=str(e),
                )
                failed += 1

        logger.info(
            "Registry loaded",
            loaded=loaded,
            failed=failed,
            total_instances=len(self._instances),
            routes=len(self._by_route),
        )

    def get(self, instance_id: str) -> DeceptionInstance | None:
        return self._instances.get(instance_id)

    def get_by_route(self, route: str) -> list[DeceptionInstance]:
        return self._by_route.get(route, [])

    def list_ids(self, limit: int | None = None) -> list[str]:
        ids = list(self._instances.keys())
        return ids[:limit] if limit else ids

    def stats(self) -> dict[str, Any]:
        channel_counts: dict[str, int] = {}
        surface_counts: dict[str, int] = {}
        primitive_counts: dict[str, int] = {}

        for instance in self._instances.values():
            channel_counts[instance.channel] = channel_counts.get(instance.channel, 0) + 1
            surface_counts[instance.surface] = surface_counts.get(instance.surface, 0) + 1
            if instance.primitive_id:
                primitive_counts[instance.primitive_id] = primitive_counts.get(instance.primitive_id, 0) + 1

        return {
            "total_instances": len(self._instances),
            "total_routes": len(self._by_route),
            "by_channel": channel_counts,
            "by_surface": surface_counts,
            "by_primitive": primitive_counts,
        }

    def __len__(self) -> int:
        return len(self._instances)

    def __contains__(self, instance_id: str) -> bool:
        return instance_id in self._instances
