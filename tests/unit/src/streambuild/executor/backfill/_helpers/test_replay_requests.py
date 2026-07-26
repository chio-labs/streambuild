from dataclasses import replace

import pytest

from streambuild.adapter.models import AdapterReplayRequest
from streambuild.adapter.types import AdapterReplayLowerBoundMode, AdapterReplaySeedMode
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.compiler.compile.models import CompiledPipeline, DesiredState
from streambuild.compiler.desired_state.main.build_desired_state import build_desired_state
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.metadata_state.models import DeploymentWatermarkRecord
from streambuild.compiler.planner.main.plan_deployment import plan_deployment
from streambuild.compiler.planner.models import ActualState, DeploymentPlan, RebuildSubtree
from streambuild.compiler.planner.types import RebuildExecutionMode
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_preservation_matrix_compiled_pipeline,
)
from tests.unit.src.streambuild.executor.backfill._helpers._test_types import (
    ReplayRequestConstructionTestCase,
)
from tests.unit.src.streambuild.executor.backfill._helpers.helpers import (
    RecordingReplayConnection,
    capture_replay_requests,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReplayRequestConstructionTestCase(
            description="builds inclusive managed offset replay request",
            source_ownership="managed",
            replay_mode=ReplayLineageMode.OFFSETS,
            boundary_key="_replay_partition=0",
            cutoff_value="10",
            expected_partition_value="0",
            expected_anchor_name="raw__orders",
            expected_partition_column="_replay_partition",
            expected_offset_column="_replay_offset",
            expected_timestamp_column="_replay_timestamp",
            expected_cursor_column="_replay_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.FULL_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.NONE,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.NONE,
        ),
        ReplayRequestConstructionTestCase(
            description="builds inclusive managed timestamp replay request",
            source_ownership="managed",
            replay_mode=ReplayLineageMode.TIMESTAMP,
            boundary_key="_replay_timestamp",
            cutoff_value="2026-04-08 13:00:00.000",
            expected_partition_value=None,
            expected_anchor_name="raw__orders",
            expected_partition_column="_replay_partition",
            expected_offset_column="_replay_offset",
            expected_timestamp_column="_replay_timestamp",
            expected_cursor_column="_replay_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.FULL_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.NONE,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.NONE,
        ),
        ReplayRequestConstructionTestCase(
            description="builds inclusive managed landed-at replay request",
            source_ownership="managed",
            replay_mode=ReplayLineageMode.LANDED_AT,
            boundary_key="_replay_landed_at",
            cutoff_value="2026-04-08 13:00:00.000",
            expected_partition_value=None,
            expected_anchor_name="raw__orders",
            expected_partition_column="_replay_partition",
            expected_offset_column="_replay_offset",
            expected_timestamp_column="_replay_timestamp",
            expected_cursor_column="_replay_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.FULL_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.NONE,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.NONE,
        ),
        ReplayRequestConstructionTestCase(
            description="builds inclusive adopted offset replay request with physical columns",
            source_ownership="adopted",
            replay_mode=ReplayLineageMode.OFFSETS,
            boundary_key="_replay_partition=0",
            cutoff_value="10",
            expected_partition_value="0",
            expected_anchor_name="orders_existing",
            expected_partition_column="event_partition",
            expected_offset_column="event_offset",
            expected_timestamp_column="event_timestamp",
            expected_cursor_column="_replay_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.FULL_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.NONE,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.NONE,
        ),
        ReplayRequestConstructionTestCase(
            description="builds inclusive adopted timestamp replay request with physical columns",
            source_ownership="adopted",
            replay_mode=ReplayLineageMode.TIMESTAMP,
            boundary_key="_replay_timestamp",
            cutoff_value="2026-04-08 13:00:00.000",
            expected_partition_value=None,
            expected_anchor_name="orders_existing",
            expected_partition_column="_replay_partition",
            expected_offset_column="_replay_offset",
            expected_timestamp_column="event_timestamp",
            expected_cursor_column="_replay_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.FULL_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.NONE,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.NONE,
        ),
        ReplayRequestConstructionTestCase(
            description="builds inclusive adopted cursor replay request with physical columns",
            source_ownership="adopted",
            replay_mode=ReplayLineageMode.CURSOR,
            boundary_key="_replay_cursor",
            cutoff_value="10",
            expected_partition_value=None,
            expected_anchor_name="orders_existing",
            expected_partition_column="_replay_partition",
            expected_offset_column="_replay_offset",
            expected_timestamp_column="event_timestamp",
            expected_cursor_column="event_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.FULL_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.NONE,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.NONE,
        ),
        ReplayRequestConstructionTestCase(
            description="builds history-prefix seeded bounded replay request",
            source_ownership="managed",
            replay_mode=ReplayLineageMode.OFFSETS,
            boundary_key="_replay_partition=0",
            cutoff_value="10",
            expected_partition_value="0",
            expected_anchor_name="raw__orders",
            expected_partition_column="_replay_partition",
            expected_offset_column="_replay_offset",
            expected_timestamp_column="_replay_timestamp",
            expected_cursor_column="_replay_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.SEEDED_BOUNDED_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.HISTORY_PREFIX,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.ACTIVE_FRONTIER,
        ),
        ReplayRequestConstructionTestCase(
            description="builds unseeded bounded scalar replay request",
            source_ownership="managed",
            replay_mode=ReplayLineageMode.TIMESTAMP,
            boundary_key="_replay_timestamp",
            cutoff_value="2026-04-08 13:00:00.000",
            expected_partition_value=None,
            expected_anchor_name="raw__orders",
            expected_partition_column="_replay_partition",
            expected_offset_column="_replay_offset",
            expected_timestamp_column="_replay_timestamp",
            expected_cursor_column="_replay_cursor",
            expected_cutoff_inclusive=True,
            expected_lower_bound_inclusive=True,
            execution_mode=RebuildExecutionMode.UNSEEDED_BOUNDED_REBUILD,
            expected_seed_mode=AdapterReplaySeedMode.NONE,
            expected_lower_bound_mode=AdapterReplayLowerBoundMode.ACTIVE_FRONTIER,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_replay_mode_when_building_request_then_boundaries_and_relations_are_neutral(
    test_case: ReplayRequestConstructionTestCase,
) -> None:
    compiled_pipeline: CompiledPipeline = build_preservation_matrix_compiled_pipeline(
        source_ownership=test_case.source_ownership,
        replay_lineage_mode=test_case.replay_mode,
    )
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    deployment_plan: DeploymentPlan = plan_deployment(
        desired_state=desired_state,
        actual_state=ActualState(objects=()),
        default_database="analytics",
        render_resource=ClickHouseAdapter().render_resource,
        deployment_id="dep",
    )
    subtree: RebuildSubtree = replace(
        deployment_plan.rebuild_subtrees[0],
        execution_mode=test_case.execution_mode,
    )
    deployment_plan = replace(deployment_plan, rebuild_subtrees=(subtree,))
    watermarks: tuple[DeploymentWatermarkRecord, ...] = (
        DeploymentWatermarkRecord(
            deployment_id="dep",
            root_key=subtree.root_key,
            anchor_key=subtree.upstream_boundary_key,
            boundary_key=test_case.boundary_key,
            cutoff_value=test_case.cutoff_value,
        ),
    )
    connection: RecordingReplayConnection = RecordingReplayConnection()

    requests: tuple[AdapterReplayRequest, ...] = capture_replay_requests(
        connection=connection,
        mode=test_case.replay_mode,
        deployment_plan=deployment_plan,
        desired_state=desired_state,
        watermarks=watermarks,
    )
    request: AdapterReplayRequest = requests[0]

    assert request.relations.anchor == test_case.expected_anchor_name
    assert request.boundaries[0].partition_value == test_case.expected_partition_value
    assert request.boundaries[0].cutoff_inclusive == test_case.expected_cutoff_inclusive
    assert request.window.lower_bound_inclusive == test_case.expected_lower_bound_inclusive
    assert request.columns.partition == test_case.expected_partition_column
    assert request.columns.offset == test_case.expected_offset_column
    assert request.columns.timestamp == test_case.expected_timestamp_column
    assert request.columns.cursor == test_case.expected_cursor_column
    assert request.seed_mode == test_case.expected_seed_mode
    assert request.window.lower_bound_mode == test_case.expected_lower_bound_mode
    assert str(request.mode) == str(test_case.replay_mode)
