"""Authored specification models and the discovery results built from them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from streambuild.compiler.discovery.constants import DEFAULT_ADAPTER_NAME
from streambuild.compiler.discovery.exceptions import ProjectSpecError
from streambuild.compiler.discovery.main._immutable_config_pairs import immutable_config_pairs
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayOnChangeMode,
    SourceKind,
)


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
class ProjectSettings:
    """Committed project-wide feature settings."""

    virtual_environments: bool = False


@dataclass(frozen=True)
class AuthoredProjectSettings:
    """Committed project-wide settings before effective interpolation."""

    virtual_environments: bool | str = False


@dataclass(frozen=True)
class LocalProjectSettings:
    """Explicit local project-wide setting overrides."""

    virtual_environments: bool | str | None = None


@dataclass(frozen=True, repr=False)
class ProjectTarget:
    """One committed named target before local resolution."""

    database: str | None = None
    connection: RawConnectionConfig = field(default_factory=RawConnectionConfig)
    variables: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True, repr=False)
class LocalProjectTarget:
    """One local named target definition or override."""

    database: str | None = None
    connection: RawConnectionConfig = field(default_factory=RawConnectionConfig)
    variables: tuple[tuple[str, object], ...] = ()

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
class ProjectReplayDefaults:
    """Committed project-wide replay policy defaults."""

    replay_on_change: ReplayOnChangePolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | None = None


@dataclass(frozen=True, repr=False)
class AuthoredProjectConfig:
    """Committed TOML project configuration before invocation resolution."""

    name: str
    adapter: str
    default_target: str
    settings: AuthoredProjectSettings
    connection: RawConnectionConfig
    variables: tuple[tuple[str, object], ...]
    targets: tuple[tuple[str, ProjectTarget], ...]
    defaults: ProjectReplayDefaults = field(default_factory=ProjectReplayDefaults)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True, repr=False)
class LocalProjectConfig:
    """Optional local TOML overrides before invocation resolution."""

    target: str | None = None
    adapter: str | None = None
    settings: LocalProjectSettings = field(default_factory=LocalProjectSettings)
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
    settings: ProjectSettings
    database: str | None
    connection: RawConnectionConfig
    variables: tuple[tuple[str, object], ...]
    defaults: ProjectReplayDefaults

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", immutable_config_pairs(self.variables))


@dataclass(frozen=True, repr=False)
class KafkaSettings:
    """Kafka engine settings for a landing step."""

    broker_list: str
    topic: str
    consumer_group: str | None = None
    format: str = "JSONAsString"
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", SourceKind(self.kind))


@dataclass(frozen=True)
class TransformStep:
    """A transform from one logical upstream node into a managed table."""

    name: str
    source: str
    engine: str
    order_by: Sequence[str]
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
class Project:
    """Effective project values retained by the current compilation model."""

    replay_on_change: ReplayOnChangePolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None
    default_database: str | None = None
    adapter: str = DEFAULT_ADAPTER_NAME

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
    source: KafkaLandingStep | ExternalTableSourceStep
    transforms: Sequence[TransformStep] = field(default_factory=tuple)
    replay_on_change: ReplayOnChangePolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "transforms", tuple(self.transforms))
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


@dataclass(frozen=True, repr=False)
class DiscoveredSourceFile:
    """One retained standalone source declaration file and its parsed sources."""

    source_file: DiscoveredProjectFile
    sources: tuple[KafkaLandingStep | ExternalTableSourceStep, ...]


@dataclass(frozen=True, repr=False)
class DiscoveredProjectInputs:
    """All raw project inputs captured before semantic compilation."""

    project_dir: Path
    loaded_project: LoadedProject | None
    source_files: tuple[DiscoveredSourceFile, ...]
    pipeline_files: tuple[DiscoveredProjectFile, ...]
    model_files: tuple[DiscoveredProjectFile, ...]
    test_files: tuple[DiscoveredProjectFile, ...]
    audit_files: tuple[DiscoveredProjectFile, ...]
    audit_schema_files: tuple[DiscoveredProjectFile, ...]
    macro_files: tuple[DiscoveredProjectFile, ...]
