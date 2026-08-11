"""Authored specification models and the discovery results built from them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from streambuild.compiler.discovery.constants import (
    DEFAULT_ADAPTER_NAME,
    DEFAULT_PIPELINE_PREFIX,
    DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS,
    DEFAULT_TABLE_PREFIX,
    DEFAULT_VIEW_PREFIX,
)
from streambuild.compiler.discovery.exceptions import ProjectSpecError
from streambuild.compiler.discovery.main._immutable_config_pairs import immutable_config_pairs
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    PipelineMode,
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayOnChangeMode,
    SourceKind,
    SourceNameOrigin,
)
from streambuild.compiler.macros.models import MacroRegistry


@dataclass(frozen=True, repr=False)
class DiscoveredProjectFile:
    """One project source file loaded exactly once during discovery."""

    file_path: Path
    relative_path: Path
    contents: str


@dataclass(frozen=True, repr=False)
class RawConnectionConfig:
    """Unexpanded adapter-owned connection values retained without secret repr output."""

    values: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", immutable_config_pairs(self.values))


@dataclass(frozen=True)
class AuditSchedulerConfig:
    """Effective target-resolved background audit scheduler configuration."""

    enabled: bool = False


@dataclass(frozen=True)
class AuditSchedulerOverride:
    """Optional authored scheduler override at target scope."""

    enabled: bool | None = None


@dataclass(frozen=True)
class BuildConfig:
    """Committed absolute limits applied before a build mutates its target."""

    max_pipelines: int | None = None


@dataclass(frozen=True, repr=False)
class ProjectTarget:
    """One committed named target before local resolution."""

    database: str | None = None
    connection: RawConnectionConfig = field(default_factory=RawConnectionConfig)
    variables: tuple[tuple[str, object], ...] = ()
    audit_scheduler: AuditSchedulerOverride = field(default_factory=AuditSchedulerOverride)
    build: BuildConfig = field(default_factory=BuildConfig)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True, repr=False)
class LocalProjectTarget:
    """One local named target definition or override."""

    database: str | None = None
    connection: RawConnectionConfig = field(default_factory=RawConnectionConfig)
    variables: tuple[tuple[str, object], ...] = ()
    audit_scheduler: AuditSchedulerOverride = field(default_factory=AuditSchedulerOverride)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True)
class ReplayOnChangeRule:
    """One breaking or non-breaking replay policy choice."""

    mode: ReplayOnChangeMode | str
    lookback_seconds: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ReplayOnChangeMode(self.mode))


@dataclass(frozen=True)
class ReplayOnChangePolicy:
    """Replay scope selected independently for breaking and non-breaking changes."""

    breaking: ReplayOnChangeRule | None = None
    non_breaking: ReplayOnChangeRule | None = None


@dataclass(frozen=True)
class SourceFreshnessPolicy:
    """Authored freshness thresholds as `<int><s|m|h|d>` durations."""

    warn_after: str | None = None
    error_after: str | None = None


@dataclass(frozen=True)
class AuditDefaults:
    """Optional project- or pipeline-level audit policy defaults."""

    severity: str | None = None
    cadence_seconds: int | None = None
    warmup_seconds: int | None = None


@dataclass(frozen=True)
class DeploymentReadinessDefaults:
    """Project-wide virtual deployment comparison thresholds."""

    maximum_lag_seconds: float = 30.0
    minimum_staged_row_ratio: float = 0.5


@dataclass(frozen=True)
class KafkaSourceDefaults:
    """Project-wide defaults for managed Kafka sources."""

    naming_macro: str | None = None


@dataclass(frozen=True)
class SourceDefaults:
    """Project-wide defaults grouped by source kind."""

    kafka: KafkaSourceDefaults = field(default_factory=KafkaSourceDefaults)


@dataclass(frozen=True)
class ProjectDefaults:
    """Committed project-wide authored defaults."""

    managed_source_ttl: str | None = None
    model_ttl: str | None = None
    kafka_broker_list: str | None = None
    pipeline_mode: PipelineMode | str = PipelineMode.DIRECT
    replay_on_change: ReplayOnChangePolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | None = None
    run_presumed_failed_after_seconds: int = DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS
    freshness: SourceFreshnessPolicy | None = None
    audits: AuditDefaults = field(default_factory=AuditDefaults)
    deployment_readiness: DeploymentReadinessDefaults = field(
        default_factory=DeploymentReadinessDefaults
    )
    sources: SourceDefaults = field(default_factory=SourceDefaults)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pipeline_mode", PipelineMode(self.pipeline_mode))


@dataclass(frozen=True)
class LocalProjectDefaults:
    """Local overrides for project-wide pipeline defaults."""

    pipeline_mode: PipelineMode | str | None = None

    def __post_init__(self) -> None:
        if self.pipeline_mode is not None:
            object.__setattr__(self, "pipeline_mode", PipelineMode(self.pipeline_mode))


@dataclass(frozen=True)
class ProjectNaming:
    """Project-wide pipeline validation and model relation naming."""

    pipeline_prefix: str = DEFAULT_PIPELINE_PREFIX
    pipeline_naming_macro: str | None = None
    table_prefix: str = DEFAULT_TABLE_PREFIX
    view_prefix: str = DEFAULT_VIEW_PREFIX


@dataclass(frozen=True)
class PipelineNaming:
    """Optional pipeline overrides for project model relation prefixes."""

    table_prefix: str | None = None
    view_prefix: str | None = None


@dataclass(frozen=True)
class PipelineProtection:
    """Operator warning and exact confirmation required before a protected build."""

    warning: str
    confirmation: str


@dataclass(frozen=True, repr=False)
class AuthoredProjectConfig:
    """Committed TOML project configuration before invocation resolution."""

    name: str
    adapter: str
    default_target: str
    connection: RawConnectionConfig
    variables: tuple[tuple[str, object], ...]
    targets: tuple[tuple[str, ProjectTarget], ...]
    defaults: ProjectDefaults = field(default_factory=ProjectDefaults)
    naming: ProjectNaming = field(default_factory=ProjectNaming)
    audit_scheduler: AuditSchedulerConfig = field(default_factory=AuditSchedulerConfig)
    build: BuildConfig = field(default_factory=BuildConfig)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True, repr=False)
class LocalProjectConfig:
    """Optional local TOML overrides before invocation resolution."""

    target: str | None = None
    adapter: str | None = None
    defaults: LocalProjectDefaults = field(default_factory=LocalProjectDefaults)
    connection: RawConnectionConfig = field(default_factory=RawConnectionConfig)
    variables: tuple[tuple[str, object], ...] = ()
    targets: tuple[tuple[str, LocalProjectTarget], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True, repr=False)
class LoadedProjectConfiguration:
    """Retained committed and optional local configuration inputs."""

    project: AuthoredProjectConfig
    local: LocalProjectConfig
    project_source: DiscoveredProjectFile
    local_source: DiscoveredProjectFile | None


@dataclass(frozen=True, repr=False)
class EffectiveProjectConfiguration:
    """One immutable connection-lazy project configuration for an invocation."""

    name: str
    adapter: str
    target_name: str
    database: str | None
    connection: RawConnectionConfig
    variables: tuple[tuple[str, object], ...]
    defaults: ProjectDefaults
    naming: ProjectNaming = field(default_factory=ProjectNaming)
    audit_scheduler: AuditSchedulerConfig = field(default_factory=AuditSchedulerConfig)
    build: BuildConfig = field(default_factory=BuildConfig)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True, repr=False)
class KafkaSettings:
    """Kafka engine settings for a landing step."""

    broker_list: str
    topic: str
    consumer_group: str | None = None
    format: str = "JSONAsString"
    ttl: str | None = None
    settings: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.settings is not None:
            object.__setattr__(self, "settings", MappingProxyType(dict(self.settings)))


@dataclass(frozen=True, repr=False)
class KafkaLandingStep:
    """A standardized Kafka landing step."""

    name: str
    kafka: KafkaSettings
    replay_boundary: ReplayBoundary | None = None
    freshness: SourceFreshnessPolicy | None = None
    name_origin: SourceNameOrigin | str = SourceNameOrigin.EXPLICIT
    naming_macro: str | None = None
    naming_macro_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name_origin", SourceNameOrigin(self.name_origin))


@dataclass(frozen=True)
class ReplayBoundaryColumns:
    """User-declared source boundary column mapping."""

    partition: str | None = None
    offset: str | None = None
    timestamp: str | None = None
    landed_at: str | None = None
    cursor: str | None = None


@dataclass(frozen=True)
class ReplayBoundary:
    """User-declared replay boundary contract for an adopted source."""

    mode: ReplayBoundaryMode | str
    columns: ReplayBoundaryColumns

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ReplayBoundaryMode(self.mode))


@dataclass(frozen=True)
class ExternalTableSourceStep:
    """A replay-driving adopted source table."""

    name: str
    kind: SourceKind | str
    table_name: str
    replay_boundary: ReplayBoundary
    freshness: SourceFreshnessPolicy | None = None
    name_origin: SourceNameOrigin | str = SourceNameOrigin.EXPLICIT

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", SourceKind(self.kind))
        object.__setattr__(self, "name_origin", SourceNameOrigin(self.name_origin))


@dataclass(frozen=True)
class ModelColumnSpec:
    """An authored MODEL(...) column declaration."""

    name: str
    description: str | None = None
    audits: tuple[object, ...] = ()


@dataclass(frozen=True)
class TransformStep:
    """A transform from one logical upstream node into a managed table."""

    name: str
    source: str
    engine: str
    order_by: Sequence[str]
    relation_name: str | None = None
    description: str | None = None
    columns: tuple[ModelColumnSpec, ...] = ()
    audits: tuple[object, ...] = ()
    query: str | None = None
    sql_file: str | None = None
    partition_by: str | None = None
    ttl: str | None = None
    settings: Mapping[str, str] | None = None
    replay_anchor: ReplayAnchorMode | str = ReplayAnchorMode.AUTO
    replay_on_change: ReplayOnChangePolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None
    source_file_path: Path | None = None
    source_line: int = 1
    source_column: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_by", tuple(self.order_by))
        if self.settings is not None:
            object.__setattr__(self, "settings", MappingProxyType(dict(self.settings)))
        object.__setattr__(self, "replay_anchor", ReplayAnchorMode(self.replay_anchor))
        if self.bounded_replay_fallback is not None:
            object.__setattr__(
                self,
                "bounded_replay_fallback",
                BoundedReplayFallback(self.bounded_replay_fallback),
            )
        if bool(self.query) == bool(self.sql_file):
            raise ProjectSpecError("Exactly one of 'query' or 'sql_file' must be provided")
        if not self.order_by:
            raise ProjectSpecError("TransformStep must declare at least one ORDER BY expression")


@dataclass(frozen=True)
class ViewStep:
    """A query-only terminal model with arbitrary logical upstreams."""

    name: str
    query: str | None = None
    sql_file: str | None = None
    relation_name: str | None = None
    description: str | None = None
    columns: tuple[ModelColumnSpec, ...] = ()
    audits: tuple[object, ...] = ()
    source_file_path: Path | None = None
    source_line: int = 1
    source_column: int = 1

    def __post_init__(self) -> None:
        if bool(self.query) == bool(self.sql_file):
            raise ProjectSpecError("Exactly one of 'query' or 'sql_file' must be provided")


@dataclass(frozen=True)
class Project:
    """Effective project values retained by the current compilation model."""

    replay_on_change: ReplayOnChangePolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None
    model_ttl: str | None = None
    default_database: str | None = None
    adapter: str = DEFAULT_ADAPTER_NAME
    naming: ProjectNaming = field(default_factory=ProjectNaming)
    audit_defaults: AuditDefaults = field(default_factory=AuditDefaults)
    audit_scheduler: AuditSchedulerConfig = field(default_factory=AuditSchedulerConfig)

    def __post_init__(self) -> None:
        if self.bounded_replay_fallback is not None:
            object.__setattr__(
                self,
                "bounded_replay_fallback",
                BoundedReplayFallback(self.bounded_replay_fallback),
            )


@dataclass(frozen=True)
class Pipeline:
    """A single authored streaming pipeline."""

    name: str
    source: KafkaLandingStep | ExternalTableSourceStep | None
    transforms: Sequence[TransformStep | ViewStep] = field(default_factory=tuple)
    mode: PipelineMode | str = PipelineMode.DIRECT
    replay_on_change: ReplayOnChangePolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None
    naming: PipelineNaming = field(default_factory=PipelineNaming)
    protection: PipelineProtection | None = None
    audit_defaults: AuditDefaults = field(default_factory=AuditDefaults)

    def __post_init__(self) -> None:
        object.__setattr__(self, "transforms", tuple(self.transforms))
        object.__setattr__(self, "mode", PipelineMode(self.mode))
        if self.bounded_replay_fallback is not None:
            object.__setattr__(
                self,
                "bounded_replay_fallback",
                BoundedReplayFallback(self.bounded_replay_fallback),
            )


@dataclass(frozen=True)
class LoadedPipeline:
    """A discovered pipeline plus the file it was loaded from."""

    pipeline: Pipeline
    file_path: Path
    project: Project | None = None


@dataclass(frozen=True, repr=False)
class LoadedProject:
    """Parsed project configuration with its retained authored source."""

    project: Project
    source_file: DiscoveredProjectFile
    configuration: LoadedProjectConfiguration | None = None
    effective_configuration: EffectiveProjectConfiguration | None = None
    source_files: tuple[DiscoveredSourceFile, ...] = ()
    macro_files: tuple[DiscoveredProjectFile, ...] = ()
    macro_registry: MacroRegistry | None = None


@dataclass(frozen=True, repr=False)
class DiscoveredSourceFile:
    """One retained standalone source declaration file and its parsed sources."""

    source_file: DiscoveredProjectFile
    sources: tuple[KafkaLandingStep | ExternalTableSourceStep, ...]


@dataclass(frozen=True, repr=False)
class DiscoveredPipelineDirectory:
    """One direct pipeline directory and its optional retained configuration."""

    pipeline_dir: Path
    config_file: DiscoveredProjectFile | None = None


@dataclass(frozen=True, repr=False)
class DiscoveredProjectInputs:
    """All raw project inputs captured before semantic compilation."""

    project_dir: Path
    loaded_project: LoadedProject | None
    source_files: tuple[DiscoveredSourceFile, ...]
    pipeline_directories: tuple[DiscoveredPipelineDirectory, ...]
    model_files: tuple[DiscoveredProjectFile, ...]
    test_files: tuple[DiscoveredProjectFile, ...]
    audit_files: tuple[DiscoveredProjectFile, ...]
    macro_files: tuple[DiscoveredProjectFile, ...]
