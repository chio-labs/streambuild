from dataclasses import dataclass
from pathlib import Path

from streambuild.spec.models.types import (
    BoundedReplayFallback,
    ReplayLineageMode,
    SchemaChangeBackfillMode,
    SourceKind,
)


@dataclass(frozen=True)
class LoadPipelineFileTestCase:
    description: str
    pipeline_file_path: Path
    expected_pipeline_name: str
    expected_source_name: str
    expected_project_replay_lineage_mode: ReplayLineageMode | None = None


@dataclass(frozen=True)
class LoadPipelineFileErrorTestCase:
    description: str
    file_contents: str
    expected_error_type: type[Exception]
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadPipelineFileProjectConfigTestCase:
    description: str
    project_file_contents: str
    pipeline_file_contents: str
    expected_pipeline_name: str
    expected_project_replay_lineage_mode: ReplayLineageMode
    expected_project_unsupported_replay_behavior: BoundedReplayFallback = (
        BoundedReplayFallback.FULL_REFRESH
    )


@dataclass(frozen=True)
class LoadPipelineFileSqlModelDefaultsTestCase:
    description: str
    sql_model_contents: str
    expected_engine: str
    expected_order_by: list[str]


@dataclass(frozen=True)
class LoadPipelineFileSchemaChangeBackfillTestCase:
    description: str
    sql_model_contents: str
    expected_breaking_mode: SchemaChangeBackfillMode
    expected_breaking_lookback_seconds: int | None
    expected_non_breaking_mode: SchemaChangeBackfillMode
    expected_non_breaking_lookback_seconds: int | None


@dataclass(frozen=True)
class LoadPipelineFileRepeatedSourceRefTestCase:
    description: str
    sql_model_contents: str
    expected_transform_source: str


@dataclass(frozen=True)
class LoadPipelineFileUnsupportedReplayBehaviorTestCase:
    description: str
    pipeline_file_contents: str
    sql_model_contents: str
    expected_pipeline_unsupported_replay_behavior: BoundedReplayFallback | None
    expected_transform_unsupported_replay_behavior: BoundedReplayFallback | None


@dataclass(frozen=True)
class LoadPipelineFileAdoptedSourceTestCase:
    description: str
    pipeline_file_contents: str
    expected_source_kind: SourceKind
    expected_table_name: str
    expected_partition_column: str
    expected_offset_column: str
    expected_timestamp_column: str


@dataclass(frozen=True)
class LoadPipelineFileInvalidAdoptedSourceTestCase:
    description: str
    pipeline_file_contents: str
    expected_error_fragment: str
