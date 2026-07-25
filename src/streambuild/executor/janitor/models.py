"""Runtime models for janitor preview."""

from dataclasses import dataclass

from streambuild.spec.models.types import ReplayLineageMode


@dataclass(frozen=True)
class JanitorPreviewCandidate:
    deployment_id: str
    created_at: str
    status: str
    logical_view_names: tuple[str, ...]
    physical_object_names: tuple[str, ...]
    deletable: bool
    reason: str


@dataclass(frozen=True)
class JanitorPreviewResult:
    database: str
    retention_days: int
    candidates: tuple[JanitorPreviewCandidate, ...]


@dataclass(frozen=True)
class JanitorApplyResult:
    database: str
    retention_days: int
    deleted_deployment_ids: tuple[str, ...]
    deleted_object_names: tuple[str, ...]


@dataclass(frozen=True)
class JanitorRequest:
    database: str
    metadata_database: str
    retention_days: int
    apply: bool


@dataclass(frozen=True)
class DeploymentMetadataRow:
    deployment_id: str
    created_at: str
    status: str
    replay_lineage_mode: ReplayLineageMode
    prepared_object_mappings_json: str


@dataclass(frozen=True)
class PublishHistoryMetadataRow:
    deployment_id: str
    latest_published_at: str
