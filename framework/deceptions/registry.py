"""
Deception instance registry: load and index resolved instances from disk.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    raise ImportError(
        "deception_runtime requires PyYAML. Install with: pip install pyyaml"
    )

from deception_runtime.logging import StructuredLogger

logger = StructuredLogger(__name__)


@dataclass
class DeceptionInstance:
    """
    A loaded deception instance with indexed access to key fields.

    Attributes:
        instance_id: Unique instance identifier
        primitive_id: Primitive template ID (optional)
        channel: Perception channel (dom, pixel, hybrid)
        surface: Perception surface (specific injection point)
        payload_text: Resolved payload content
        placement: Placement configuration dict
        honeytoken: Honeytoken configuration dict or None
        raw: Full raw instance data
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

        Args:
            data: Parsed YAML data
            source_file: Source file path for error messages

        Returns:
            DeceptionInstance

        Raises:
            ValueError: If required fields are missing
        """
        # Required fields
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
        # payload.content_template should already be resolved
        payload_text = payload.get("content_template", "")

        placement = data.get("placement", {})
        honeytoken = data.get("honeytoken")

        # primitive_id might be in metadata or top-level
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
        """
        Initialize the registry.

        Args:
            instances_dir: Directory containing *.resolved.yaml files
            schema_path: Optional path to JSON schema for validation
            validate_schema: Whether to validate against schema (requires jsonschema)
        """
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

            # Remove metadata fields before validation
            clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
            jsonschema.validate(instance=clean_data, schema=self._schema)
        except ImportError:
            # jsonschema not available, skip validation
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

                # Optional schema validation
                self._validate_instance(data, str(yaml_file))

                # Parse into DeceptionInstance
                instance = DeceptionInstance.from_dict(data, str(yaml_file))

                # Check for duplicate IDs
                if instance.instance_id in self._instances:
                    logger.warning(
                        "Duplicate instance_id found, overwriting",
                        instance_id=instance.instance_id,
                        file=str(yaml_file),
                    )

                # Store in main index
                self._instances[instance.instance_id] = instance

                # Index by route if present
                if instance.route:
                    if instance.route not in self._by_route:
                        self._by_route[instance.route] = []
                    self._by_route[instance.route].append(instance)

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
        """
        Get instance by ID.

        Args:
            instance_id: Instance identifier

        Returns:
            DeceptionInstance or None if not found
        """
        return self._instances.get(instance_id)

    def get_by_route(self, route: str) -> list[DeceptionInstance]:
        """
        Get all instances for a specific route.

        Args:
            route: Route path (e.g., "/login")

        Returns:
            List of DeceptionInstances (empty if none found)
        """
        return self._by_route.get(route, [])

    def list_ids(self, limit: int | None = None) -> list[str]:
        """
        List all instance IDs.

        Args:
            limit: Optional limit on number of IDs to return

        Returns:
            List of instance IDs
        """
        ids = list(self._instances.keys())
        if limit:
            return ids[:limit]
        return ids

    def stats(self) -> dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with counts by channel, surface, and other metrics
        """
        channel_counts: dict[str, int] = {}
        surface_counts: dict[str, int] = {}
        primitive_counts: dict[str, int] = {}

        for instance in self._instances.values():
            # Count by channel
            channel_counts[instance.channel] = channel_counts.get(instance.channel, 0) + 1

            # Count by surface
            surface_counts[instance.surface] = surface_counts.get(instance.surface, 0) + 1

            # Count by primitive_id
            if instance.primitive_id:
                primitive_counts[instance.primitive_id] = (
                    primitive_counts.get(instance.primitive_id, 0) + 1
                )

        return {
            "total_instances": len(self._instances),
            "total_routes": len(self._by_route),
            "by_channel": channel_counts,
            "by_surface": surface_counts,
            "by_primitive": primitive_counts,
        }

    def __len__(self) -> int:
        """Return number of loaded instances."""
        return len(self._instances)

    def __contains__(self, instance_id: str) -> bool:
        """Check if instance_id exists in registry."""
        return instance_id in self._instances
