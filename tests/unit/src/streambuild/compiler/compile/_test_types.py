from dataclasses import dataclass

from streambuild.spec.models import Pipeline
from streambuild.spec.types import (
    BoundedReplayFallback,
    ReplayAnchorMode,
    ReplayLineageMode,
)


@dataclass(frozen=True)
class CompilePipelineInlineRefsTestCase:
    description: str
    pipeline_file_path: str
    expected_relation_names: dict[str, str]
    expected_kafka_table_name: str
    expected_raw_table_name: str
    expected_landing_mv_name: str
    expected_landing_query_fragments: tuple[str, ...]
    expected_refs: tuple[str, ...]
    expected_query_fragment: str
    expected_target_table_name: str
    expected_transform_mv_name: str
    expected_desired_state_ordered_keys: tuple[tuple[str | None, str, str], ...]


@dataclass(frozen=True)
class CompilePipelineSqlFileTestCase:
    description: str
    sql_relative_path: str
    sql_contents: str
    expected_resolved_query: str


@dataclass(frozen=True)
class CompilePipelineInlineSqlSuccessTestCase:
    description: str
    transform_query: str
    expected_output_columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CompilePipelineMissingSourceRefTestCase:
    description: str
    transform_query: str
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class CompilePipelineInvalidTransformSqlTestCase:
    description: str
    transform_query: str
    expected_error_type: type[Exception]
    expected_message_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineInvalidTransformSqlFileTestCase:
    description: str
    sql_relative_path: str
    sql_contents: str
    expected_error_type: type[Exception]
    expected_message_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineInvalidOrderByTestCase:
    description: str
    transform_query: str
    order_by: tuple[str, ...]
    expected_error_type: type[Exception]
    expected_message_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineSqlModelDefaultOrderByTestCase:
    description: str
    sql_contents: str
    expected_error_type: type[Exception]
    expected_message_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineAdditionalRefDependencyTestCase:
    description: str
    query: str
    expected_materialized_view_deps: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineInvalidPartitionByTestCase:
    description: str
    transform_query: str
    partition_by: str
    expected_error_type: type[Exception]
    expected_message_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineInvalidTtlTestCase:
    description: str
    transform_query: str
    ttl: str
    expected_error_type: type[Exception]
    expected_message_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineMissingRefTypeTestCase:
    description: str
    transform_query: str
    expected_error_type: type[Exception]
    expected_error_fragment: str


@dataclass(frozen=True)
class CompilePipelineRepeatedSourceRefTestCase:
    description: str
    transform_query: str
    expected_target_name: str


@dataclass(frozen=True)
class CompilePipelineReplayLineageModeTestCase:
    description: str
    pipeline_replay_lineage_mode: ReplayLineageMode | str | None
    project_replay_lineage_mode: ReplayLineageMode | str | None
    expected_effective_replay_lineage_mode: ReplayLineageMode


@dataclass(frozen=True)
class CompilePipelineUnsupportedReplayBehaviorTestCase:
    description: str
    transform_unsupported_replay_behavior: BoundedReplayFallback | str | None
    pipeline_unsupported_replay_behavior: BoundedReplayFallback | str | None
    project_unsupported_replay_behavior: BoundedReplayFallback | str | None
    expected_effective_unsupported_replay_behavior: BoundedReplayFallback


@dataclass(frozen=True)
class CompilePipelineReplayAnchorEligibilityTestCase:
    description: str
    transform_query: str
    replay_lineage_mode: ReplayLineageMode | str
    engine: str = "MergeTree()"
    replay_anchor: ReplayAnchorMode | str = "auto"
    order_by: tuple[str, ...] = ("order_id",)
    supporting_transforms: tuple[tuple[str, str], ...] = ()
    expected_has_mutable_refs: bool = False
    expected_has_aggregate_semantics: bool = False
    expected_preserves_required_lineage: bool = False
    expected_replay_anchor_eligible: bool = False


@dataclass(frozen=True)
class CompilePipelineAdoptedSourceTestCase:
    description: str
    pipeline_file_contents: str
    sql_contents: str
    expected_source_relation_name: str


@dataclass(frozen=True)
class CompilePipelineReplaySurfaceTestCase:
    description: str
    pipeline: Pipeline
    expected_query_fragments: tuple[str, ...]
    expected_output_column_names: tuple[str, ...]


@dataclass(frozen=True)
class CompilePipelineReplayLineageModeResolutionTestCase:
    description: str
    pipeline: Pipeline
    expected_replay_lineage_mode: ReplayLineageMode
