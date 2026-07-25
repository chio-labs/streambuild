from dataclasses import dataclass

from streambuild.compiler.planner.types import (
    PlannedChangeType,
    RebuildExecutionMode,
    TableSchemaChangeKind,
    TableSchemaSeedCompatibility,
)


@dataclass(frozen=True)
class PlannerNoOpAfterPublishIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_rebuild_subtrees: tuple[object, ...]
    expected_steps: tuple[object, ...]


@dataclass(frozen=True)
class PlannerNormalizedTypeNoOpIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_change_type: PlannedChangeType


@dataclass(frozen=True)
class PlannerSqlChangeAfterPublishIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_rebuild_root_names: tuple[str, ...]


@dataclass(frozen=True)
class PlannerSchemaChangeAfterPublishIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    changed_pipeline_kind: str
    expected_rebuild_root_names: tuple[str, ...]
    expected_sql_diff_names: tuple[str, ...]
    expected_schema_change_kind: TableSchemaChangeKind | None
    expected_seed_compatibility: TableSchemaSeedCompatibility | None
    expected_execution_mode: RebuildExecutionMode
