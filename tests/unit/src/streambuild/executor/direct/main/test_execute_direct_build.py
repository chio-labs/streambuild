from pathlib import Path

import pytest

from streambuild.adapter.models import AdapterOwnershipRecord, AdapterReplayCoverageRange
from streambuild.adapter.types import AdapterOwningMode, AdapterReplayBoundaryMode
from streambuild.executor.direct._helpers.relations import target_relation_name_by_model_name
from streambuild.executor.direct._helpers.retention import resolve_required_replay_coverage
from streambuild.executor.direct.exceptions import DirectBuildError
from streambuild.executor.direct.main.execute_direct_build import execute_direct_build
from streambuild.executor.direct.models import (
    DirectBuildRequest,
    DirectBuildResult,
    DirectReplayCoverage,
)
from tests.unit.src.streambuild.executor.direct.main._test_types import (
    EmptyReplayNoOpTestCase,
    ExecuteDirectBuildTestCase,
    ReplayCoverageInputChangeTestCase,
)
from tests.unit.src.streambuild.executor.direct.main.helpers import (
    EmptyReplayDirectBuildConnection,
    RecordingDirectBuildConnection,
    build_direct_execution_request,
    build_direct_view_execution_request,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EmptyReplayNoOpTestCase(
            description="empty replay roots succeed without completion or coverage refresh",
            expected_replay_result_count=0,
            expected_preserved_coverage_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_replay_input_when_building_then_preflight_coverage_remains_claimed(
    test_case: EmptyReplayNoOpTestCase, tmp_path: Path
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path, selected_model_names=("beta",)
    )
    preflight_coverage: tuple[DirectReplayCoverage, ...] = tuple(
        DirectReplayCoverage(
            model_name=root.model_key.name,
            driving_input_replay_columns=root.driving_input_replay_columns,
            ranges=(
                AdapterReplayCoverageRange(
                    driving_input_relation_name=root.driving_input_relation_name,
                    replay_boundary_mode=AdapterReplayBoundaryMode.OFFSETS,
                    boundary_key="_replay_partition=0",
                    source_partition_column_name=root.driving_input_replay_columns.partition,
                    source_position_column_name=root.driving_input_replay_columns.offset,
                    source_timestamp_column_name=root.driving_input_replay_columns.timestamp,
                    lower_value="1",
                    upper_value="5",
                ),
            ),
        )
        for root in request.plan.replay_roots
    )
    existing_ownership: tuple[AdapterOwnershipRecord, ...] = tuple(
        AdapterOwnershipRecord(
            database_name=request.database,
            relation_name=f"existing__{coverage.model_name}",
            resource_kind="table",
            logical_model_name=coverage.model_name,
            owning_mode=AdapterOwningMode.DIRECT,
            tool_version="test",
            replay_coverage=coverage.ranges,
        )
        for coverage in preflight_coverage
    )
    connection: EmptyReplayDirectBuildConnection = EmptyReplayDirectBuildConnection(
        existing_ownership
    )

    result: DirectBuildResult = execute_direct_build(request=request, client=connection)

    finalized_coverages: frozenset[tuple[AdapterReplayCoverageRange, ...]] = frozenset(
        record.replay_coverage for record in result.ownership_records
    )
    assert len(result.replay_results) == test_case.expected_replay_result_count
    assert connection.replay_requests == []
    assert result.boundaries == ()
    assert len(preflight_coverage) == test_case.expected_preserved_coverage_count
    assert frozenset(coverage.ranges for coverage in preflight_coverage) <= finalized_coverages


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteDirectBuildTestCase(
            description="planned relation actions execute in dependency-safe order",
            selected_model_names=("beta",),
            expected_drop_statements=(
                "DROP TABLE IF EXISTS analytics.mv__delta SYNC",
                "DROP TABLE IF EXISTS analytics.mv__gamma SYNC",
                "DROP TABLE IF EXISTS analytics.mv__beta SYNC",
                "DROP TABLE IF EXISTS analytics.tbl__delta SYNC",
                "DROP TABLE IF EXISTS analytics.tbl__gamma SYNC",
                "DROP TABLE IF EXISTS analytics.tbl__beta SYNC",
            ),
            expected_created_relation_names=(
                "tbl__beta",
                "mv__beta",
                "tbl__gamma",
                "tbl__delta",
                "mv__delta",
                "mv__gamma",
            ),
            expected_realized_relation_names=(
                "kafka__orders",
                "raw__orders",
                "tbl__beta",
                "mv__beta",
                "tbl__gamma",
                "tbl__delta",
                "mv__delta",
                "mv__gamma",
                "mv__orders",
            ),
            expected_replay_relations=(
                ("tbl__beta", "tbl__alpha", "tbl__beta"),
                ("tbl__delta", "tbl__alpha", "tbl__delta"),
            ),
            expected_replay_query_fragments=(
                "tbl__alpha",
                "analytics.tbl__gamma",
            ),
            expected_replay_written_rows=(7, 7),
            expected_ownership_record_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_build_plan_when_executing_then_adapter_actions_match_plan_order(
    test_case: ExecuteDirectBuildTestCase, tmp_path: Path
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path, selected_model_names=test_case.selected_model_names
    )
    connection: RecordingDirectBuildConnection = RecordingDirectBuildConnection()

    result: DirectBuildResult = execute_direct_build(request=request, client=connection)

    drop_start: int = connection.adapter_actions.index(test_case.expected_drop_statements[0])
    drop_end: int = drop_start + len(test_case.expected_drop_statements)
    assert connection.adapter_actions.index("record_ownership") < drop_start
    assert (
        tuple(connection.adapter_actions[drop_start:drop_end]) == test_case.expected_drop_statements
    )
    assert result.dropped_relation_names == tuple(
        operation.relation_name for operation in request.plan.teardown_operations
    )
    assert result.created_relation_names == test_case.expected_created_relation_names
    assert tuple(connection.realized_resource_names) == test_case.expected_realized_relation_names
    assert (
        tuple(
            (request.relations.root, request.relations.anchor, request.relations.target)
            for request in connection.replay_requests
        )
        == test_case.expected_replay_relations
    )
    assert tuple(
        fragment in request.replay_query.query
        for fragment, request in zip(
            test_case.expected_replay_query_fragments,
            connection.replay_requests,
            strict=True,
        )
    ) == tuple(True for _fragment in test_case.expected_replay_query_fragments)
    assert tuple(replay.written_rows for replay in result.replay_results) == (
        test_case.expected_replay_written_rows
    )
    first_ownership_index: int = connection.adapter_actions.index("record_ownership")
    completed_ownership_index: int = connection.adapter_actions.index(
        "record_ownership", first_ownership_index + 1
    )
    assert connection.adapter_actions.count("record_ownership") == (
        test_case.expected_ownership_record_count
    )
    assert completed_ownership_index > connection.adapter_actions.index("replay:tbl__delta")


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteDirectBuildTestCase(
            description="ordinary view build creates ownership without replay activity",
            selected_model_names=("customer_orders",),
            expected_drop_statements=("DROP VIEW IF EXISTS analytics.customer_orders SYNC",),
            expected_created_relation_names=("customer_orders",),
            expected_realized_relation_names=(
                "kafka__orders",
                "raw__orders",
                "customer_orders",
                "mv__orders",
            ),
            expected_replay_relations=(),
            expected_replay_query_fragments=(),
            expected_replay_written_rows=(),
            expected_ownership_record_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_view_only_direct_build_when_executing_then_view_is_replaced_without_replay(
    test_case: ExecuteDirectBuildTestCase, tmp_path: Path
) -> None:
    request: DirectBuildRequest = build_direct_view_execution_request(project_root=tmp_path)
    connection: RecordingDirectBuildConnection = RecordingDirectBuildConnection()

    result: DirectBuildResult = execute_direct_build(request=request, client=connection)

    assert test_case.expected_drop_statements[0] in connection.adapter_actions
    assert result.created_relation_names == test_case.expected_created_relation_names
    assert connection.replay_requests == []
    assert result.boundaries == ()
    assert result.replay_results == ()
    assert tuple(record.resource_kind for record in result.ownership_records) == ("view",)
    assert connection.adapter_actions.count("record_ownership") == (
        test_case.expected_ownership_record_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReplayCoverageInputChangeTestCase(
            description="durable coverage from another driving input is rejected",
            persisted_driving_input_relation_name="tbl__old_alpha",
            persisted_partition_column_name="_replay_partition",
            persisted_position_column_name="_replay_offset",
            persisted_timestamp_column_name="_replay_timestamp",
            expected_error_fragment="driving input, replay mode, or physical mapping changed",
        ),
        ReplayCoverageInputChangeTestCase(
            description="durable coverage from another physical mapping is rejected",
            persisted_driving_input_relation_name="tbl__alpha",
            persisted_partition_column_name="old_partition",
            persisted_position_column_name="old_offset",
            persisted_timestamp_column_name="_replay_timestamp",
            expected_error_fragment="driving input, replay mode, or physical mapping changed",
        ),
        ReplayCoverageInputChangeTestCase(
            description="durable coverage from another timestamp mapping is rejected",
            persisted_driving_input_relation_name="tbl__alpha",
            persisted_partition_column_name="_replay_partition",
            persisted_position_column_name="_replay_offset",
            persisted_timestamp_column_name="old_timestamp",
            expected_error_fragment="driving input, replay mode, or physical mapping changed",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_changed_replay_contract_when_resolving_coverage_then_it_is_rejected(
    test_case: ReplayCoverageInputChangeTestCase, tmp_path: Path
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path, selected_model_names=("beta",)
    )
    connection: RecordingDirectBuildConnection = RecordingDirectBuildConnection()
    existing_ownership: tuple[AdapterOwnershipRecord, ...] = (
        AdapterOwnershipRecord(
            database_name=request.database,
            relation_name="tbl__beta",
            resource_kind="table",
            logical_model_name="beta",
            owning_mode=AdapterOwningMode.DIRECT,
            tool_version="test",
            replay_coverage=(
                AdapterReplayCoverageRange(
                    driving_input_relation_name=test_case.persisted_driving_input_relation_name,
                    replay_boundary_mode=AdapterReplayBoundaryMode.OFFSETS,
                    boundary_key="_replay_partition=0",
                    source_partition_column_name=test_case.persisted_partition_column_name,
                    source_position_column_name=test_case.persisted_position_column_name,
                    source_timestamp_column_name=test_case.persisted_timestamp_column_name,
                    lower_value="1",
                    upper_value="2",
                ),
            ),
        ),
    )

    with pytest.raises(DirectBuildError, match=test_case.expected_error_fragment):
        resolve_required_replay_coverage(
            client=connection,
            plan=request.plan,
            database=request.database,
            existing_relation_names=frozenset(),
            existing_ownership=existing_ownership,
            target_relation_name_by_model_name=target_relation_name_by_model_name(
                plan=request.plan
            ),
        )
