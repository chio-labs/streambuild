"""Metadata-state runtime models."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.compile.models import ObjectKey
from streambuild.spec.types import ReplayLineageMode


@dataclass(frozen=True)
class PreparedObjectMapping:
    """A logical-to-physical prepared object mapping for a deployment."""

    logical_key: ObjectKey
    physical_name: str


@dataclass(frozen=True)
class ObjectStateRecord:
    """Framework-owned applied state for a logical object."""

    deployment_id: str
    key: ObjectKey
    normalized_fingerprint: str
    normalized_query: str | None
    recorded_at: str


@dataclass(frozen=True)
class DeploymentRecord:
    """Stored staged deployment metadata."""

    deployment_id: str
    created_at: str
    status: str
    replay_lineage_mode: ReplayLineageMode | str
    selected_root_keys: tuple[ObjectKey, ...]
    warning_codes: tuple[str, ...]
    prepared_object_mappings: tuple[PreparedObjectMapping, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_lineage_mode", ReplayLineageMode(self.replay_lineage_mode))


@dataclass(frozen=True)
class DeploymentWatermarkRecord:
    """Stored replay-boundary or progress metadata for a deployment."""

    deployment_id: str
    root_key: ObjectKey
    anchor_key: ObjectKey
    boundary_key: str
    cutoff_value: str


@dataclass(frozen=True)
class DeploymentRuntimeDetailRecord:
    """Stored per-root runtime decision metadata for a deployment."""

    deployment_id: str
    root_key: ObjectKey
    state_kind: str
    replay_strategy: str
    active_deployment_id: str | None
    anchor_key: ObjectKey
    anchor_physical_name: str | None
    execution_mode: str | None
    configured_backfill_mode: str | None
    execution_lookback_seconds: int | None
    live_target_names: tuple[str, ...]


@dataclass(frozen=True)
class PublishEventRecord:
    """Stored publish/activation history for one deployment."""

    deployment_id: str
    published_at: str
    logical_view_names: tuple[str, ...]


@dataclass(frozen=True)
class MetadataState:
    """Project-level stored metadata-state records."""

    object_states: tuple[ObjectStateRecord, ...]
    deployments: tuple[DeploymentRecord, ...]
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...]
    deployment_runtime_details: tuple[DeploymentRuntimeDetailRecord, ...]
    publish_events: tuple[PublishEventRecord, ...]
