"""Audit backfill runtime models."""

from dataclasses import dataclass

from streambuild.compiler.compile.models import ObjectKey
from streambuild.executor.audit_backfill.types import AuditAssessment
from streambuild.executor.auditing.models import SqlAuditResult
from streambuild.spec.types import ReplayLineageMode


@dataclass(frozen=True)
class AuditBackfillRequest:
    """Input required to audit a staged backfill deployment."""

    deployment_id: str | None
    metadata_database: str
    default_database: str


@dataclass(frozen=True)
class AuditDeploymentCandidate:
    """A deployment candidate surfaced when audit resolution is ambiguous."""

    deployment_id: str
    created_at: str | None = None
    deployment_status: str | None = None
    root_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadedAuditDeployment:
    """Persisted deployment metadata used by metadata-backed flows."""

    deployment_id: str
    created_at: str
    status: str
    replay_lineage_mode: ReplayLineageMode | str | None
    warning_codes: tuple[str, ...]
    root_keys: tuple[ObjectKey, ...]
    prepared_object_mappings: tuple[tuple[ObjectKey, str], ...]

    def __post_init__(self) -> None:
        if self.replay_lineage_mode is not None:
            object.__setattr__(
                self,
                "replay_lineage_mode",
                ReplayLineageMode(self.replay_lineage_mode),
            )


@dataclass(frozen=True)
class OffsetCatchupSummary:
    """Partitioned catch-up metrics for offset-based replay."""

    active_partition_count: int
    staged_partition_count: int
    partitions_compared: int
    missing_staged_partition_count: int
    missing_freshness_partition_count: int
    lagging_partition_count: int
    max_offset_gap: int
    average_offset_gap: float
    lag_boundary_column: str | None
    max_lag_seconds: float | None
    average_lag_seconds: float | None


@dataclass(frozen=True)
class ScalarCatchupSummary:
    """Scalar catch-up metrics for timestamp-based replay."""

    active_min_value: str | None
    active_max_value: str | None
    staged_min_value: str | None
    staged_max_value: str | None
    lag_seconds: float | None


@dataclass(frozen=True)
class RootAuditResult:
    """Audit summary for one rebuilt root target."""

    root_key: ObjectKey
    staged_physical_name: str
    staged_exists: bool
    active_exists: bool
    active_row_count: int | None
    staged_row_count: int | None
    row_delta: int | None
    row_ratio: float | None
    assessment: AuditAssessment | str
    replay_lineage_mode: ReplayLineageMode | str | None
    offset_catchup_summary: OffsetCatchupSummary | None
    scalar_catchup_summary: ScalarCatchupSummary | None
    state: str
    replay_source_name: str | None
    replay_source_row_count: int | None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessment", AuditAssessment(self.assessment))
        if self.replay_lineage_mode is not None:
            object.__setattr__(
                self,
                "replay_lineage_mode",
                ReplayLineageMode(self.replay_lineage_mode),
            )


@dataclass(frozen=True)
class AuditBackfillResult:
    """Structured audit result for a staged backfill deployment."""

    deployment_id: str
    deployment_status: str
    assessment: AuditAssessment | str
    replay_lineage_mode: ReplayLineageMode | str | None
    warning_codes: tuple[str, ...]
    root_results: tuple[RootAuditResult, ...]
    quality_check_results: tuple[SqlAuditResult, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessment", AuditAssessment(self.assessment))
        if self.replay_lineage_mode is not None:
            object.__setattr__(
                self,
                "replay_lineage_mode",
                ReplayLineageMode(self.replay_lineage_mode),
            )


@dataclass(frozen=True)
class DeploymentMetadataRow:
    """Row shape for deployment metadata needed by audit flows."""

    created_at: str
    status: str
    replay_lineage_mode: ReplayLineageMode | str
    selected_root_keys_json: str
    warning_codes_json: str
    prepared_object_mappings_json: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_lineage_mode", ReplayLineageMode(self.replay_lineage_mode))


@dataclass(frozen=True)
class CountQueryRow:
    """Row shape for single-value count projections."""

    value: int


@dataclass(frozen=True)
class ColumnNameSystemRow:
    """Row shape for system column-name lookups."""

    name: str


@dataclass(frozen=True)
class OffsetSummaryQueryRow:
    """Row shape for offset replay catch-up summaries."""

    active_partition_count: int
    staged_partition_count: int
    partitions_compared: int
    missing_staged_partition_count: int
    missing_freshness_partition_count: int
    lagging_partition_count: int
    max_offset_gap: int
    average_offset_gap: float
    max_lag_seconds: float | None
    average_lag_seconds: float | None


@dataclass(frozen=True)
class ScalarSummaryQueryRow:
    """Row shape for timestamp replay catch-up summaries."""

    active_min_value: str | None
    active_max_value: str | None
    staged_min_value: str | None
    staged_max_value: str | None
    lag_seconds: float | None


@dataclass(frozen=True)
class CreateTableQueryRow:
    """Row shape for create-table DDL lookups from system tables."""

    create_table_query: str
