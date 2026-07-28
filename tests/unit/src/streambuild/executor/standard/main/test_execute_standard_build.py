from pathlib import Path

import pytest

from streambuild.adapter.models import AdapterOwnershipRecord, AdapterReplayCoverageRange
from streambuild.adapter.types import AdapterOwningMode, AdapterReplayBoundaryMode
from streambuild.executor.standard._helpers.relations import target_relation_name_by_model_name
from streambuild.executor.standard._helpers.retention import resolve_required_replay_coverage
from streambuild.executor.standard.exceptions import StandardBuildError
from streambuild.executor.standard.main.execute_standard_build import execute_standard_build
from streambuild.executor.standard.models import StandardBuildRequest, StandardBuildResult
from tests.unit.src.streambuild.executor.standard.main._test_types import (
    ExecuteStandardBuildTestCase,
    ReplayCoverageInputChangeTestCase,
)
from tests.unit.src.streambuild.executor.standard.main.helpers import (
    RecordingStandardBuildConnection,
    build_standard_execution_request,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteStandardBuildTestCase(
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
                "tbl__gamma",
                "tbl__delta",
                "mv__beta",
                "mv__gamma",
                "mv__delta",
            ),
            expected_replay_relations=(
                ("tbl__beta", "tbl__alpha", "tbl__beta"),
                ("tbl__gamma", "tbl__beta", "tbl__gamma"),
                ("tbl__delta", "tbl__alpha", "tbl__delta"),
            ),
            expected_replay_query_fragments=(
                "tbl__alpha",
                "tbl__beta",
                "analytics.tbl__gamma",
            ),
            expected_ownership_record_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_standard_build_plan_when_executing_then_adapter_actions_match_plan_order(
    test_case: ExecuteStandardBuildTestCase, tmp_path: Path
) -> None:
    request: StandardBuildRequest = build_standard_execution_request(
        project_root=tmp_path, selected_model_names=test_case.selected_model_names
    )
    connection: RecordingStandardBuildConnection = RecordingStandardBuildConnection()

    result: StandardBuildResult = execute_standard_build(request=request, client=connection)

    drop_start: int = connection.adapter_actions.index(test_case.expected_drop_statements[0])
    drop_end: int = drop_start + len(test_case.expected_drop_statements)
    create_count: int = len(test_case.expected_created_relation_names)
    assert connection.adapter_actions.index("record_ownership") < drop_start
    assert (
        tuple(connection.adapter_actions[drop_start:drop_end]) == test_case.expected_drop_statements
    )
    assert result.dropped_relation_names == tuple(
        operation.relation_name for operation in request.plan.teardown_operations
    )
    assert result.created_relation_names == test_case.expected_created_relation_names
    assert (
        tuple(connection.realized_resource_names[-create_count:])
        == test_case.expected_created_relation_names
    )
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
    ) == (True, True, True)
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
    request: StandardBuildRequest = build_standard_execution_request(
        project_root=tmp_path, selected_model_names=("beta",)
    )
    connection: RecordingStandardBuildConnection = RecordingStandardBuildConnection()
    existing_ownership: tuple[AdapterOwnershipRecord, ...] = (
        AdapterOwnershipRecord(
            database_name=request.database,
            relation_name="tbl__beta",
            resource_kind="table",
            logical_model_name="beta",
            owning_mode=AdapterOwningMode.STANDARD,
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

    with pytest.raises(StandardBuildError, match=test_case.expected_error_fragment):
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
