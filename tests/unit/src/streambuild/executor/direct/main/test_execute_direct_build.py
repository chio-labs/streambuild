import json
from pathlib import Path

import pytest

from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import AdapterDirectFingerprintRecord
from streambuild.cli.plan.main._render_direct_plan_json import render_direct_plan_json
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.compiler.compile.main.build_model_storage_identity import (
    build_model_storage_identity,
)
from streambuild.compiler.compile.models import CompiledModel
from streambuild.executor.direct.exceptions import DirectWorkflowExecutionError
from streambuild.executor.direct.main.assemble_direct_build_workflow import (
    assemble_direct_build_workflow,
)
from streambuild.executor.direct.main.execute_direct_build_workflow import (
    execute_direct_build_workflow,
)
from streambuild.executor.direct.main.persist_direct_fingerprints import (
    persist_direct_fingerprints,
)
from streambuild.executor.direct.models import (
    DirectBuildRequest,
    DirectBuildWorkflow,
    DirectRuntimeExecution,
)
from streambuild.executor.workflow.models import (
    BuildWorkflow,
    PublishedBuildWorkflow,
    WarehouseStatement,
)
from streambuild.executor.workflow.types import WorkflowPhase
from tests.unit.src.streambuild.executor.direct.main._test_types import (
    DirectCaptureValidationTestCase,
    DirectDistinctCaptureTestCase,
    DirectFingerprintMetadataTestCase,
    DirectFingerprintPersistenceTestCase,
    DirectSourceScopeTestCase,
    DirectWorkflowTestCase,
)
from tests.unit.src.streambuild.executor.direct.main.helpers import (
    DeniedFingerprintRenderingConnection,
    DistinctCaptureDirectBuildConnection,
    InvalidOffsetCaptureDirectBuildConnection,
    MismatchedCaptureDirectBuildConnection,
    RecordingDirectBuildConnection,
    RecordingFingerprintConnection,
    build_direct_execution_request,
    build_direct_execution_request_with_unrelated_pipeline,
    build_direct_execution_snapshot,
)
from tests.unit.src.streambuild.executor.workflow.helpers import (
    FailingPreparationEmitter,
    RecordingWorkflowEmitter,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceScopeTestCase(
            description="selected closure prepares only its managed source",
            expected_source_step_ids=(
                "prepare_source_kafka__orders",
                "prepare_source_raw__orders",
                "activate_source_mv__orders",
            ),
            unexpected_source_step_ids=(
                "prepare_source_kafka__unrelated",
                "prepare_source_raw__unrelated",
                "activate_source_mv__unrelated",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_direct_closure_when_assembling_then_unrelated_sources_are_omitted(
    test_case: DirectSourceScopeTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request_with_unrelated_pipeline(
        project_root=tmp_path,
        selected_model_names=("alpha",),
    )
    workflow: DirectBuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=RecordingDirectBuildConnection(),
        snapshot=build_direct_execution_snapshot(),
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )

    step_ids: set[str] = {statement.step_id for statement in workflow.statements}
    assert set(test_case.expected_source_step_ids) <= step_ids
    assert set(test_case.unexpected_source_step_ids).isdisjoint(step_ids)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectWorkflowTestCase(
            description="direct workflow publishes and executes exact ordered statement bytes",
            expected_first_phase=WorkflowPhase.PREPARATION,
            expected_last_phase=WorkflowPhase.REPLAY,
            expected_replay_count=2,
            expected_boundary_model_segments=("beta", "delta"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_plan_when_assembling_then_complete_exact_workflow_is_authoritative(
    test_case: DirectWorkflowTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=("beta",),
    )
    connection: RecordingDirectBuildConnection = RecordingDirectBuildConnection()
    workflow: DirectBuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=connection,
        snapshot=build_direct_execution_snapshot(),
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )
    emitter: RecordingWorkflowEmitter = RecordingWorkflowEmitter()
    runtime_execution: DirectRuntimeExecution = execute_direct_build_workflow(
        workflow=workflow,
        connection=connection,
        emitter=emitter,
    )
    exact_workflow: BuildWorkflow = runtime_execution.workflow
    published: PublishedBuildWorkflow = publish_build_workflow(
        target_dir=tmp_path / "target",
        workflow=exact_workflow,
    )

    statements: tuple[WarehouseStatement, ...] = exact_workflow.statements
    all_sql: tuple[str, ...] = tuple(statement.sql for statement in statements)
    step_bytes: tuple[str, ...] = tuple(
        path.read_text(encoding="utf-8")
        for path in sorted((published.artifact_root / "steps").iterdir())
    )
    assert statements[0].phase == test_case.expected_first_phase
    assert statements[-1].phase == test_case.expected_last_phase
    assert tuple(statement.sequence for statement in statements) == tuple(
        range(1, len(statements) + 1)
    )
    assert all(
        statement.sql.endswith(";") and not statement.sql.endswith(";;") for statement in statements
    )
    assert sum(statement.step_id.startswith("replay_") for statement in statements) == (
        test_case.expected_replay_count
    )
    expected_boundary_windows: tuple[tuple[str, ...], ...] = tuple(
        (
            f"capture_replay_{model_segment}",
            f"replay_{model_segment}",
        )
        for model_segment in test_case.expected_boundary_model_segments
    )
    expected_runtime_step_ids: tuple[str, ...] = sum(expected_boundary_windows, ())
    actual_runtime_step_ids: tuple[str, ...] = tuple(
        statement.step_id for statement in statements[-len(expected_runtime_step_ids) :]
    )
    assert actual_runtime_step_ids == expected_runtime_step_ids
    assert step_bytes == tuple(statement.sql for statement in statements)
    assert (published.artifact_root / "workflow.sql").read_text(encoding="utf-8") == (
        "\n".join(statement.sql for statement in statements)
    )
    assert connection.catalog_databases == []
    assert set(connection.workflow_mutation_statements) <= set(all_sql)
    assert emitter.prepared_workflows[0] == workflow.statements
    assert emitter.prepared_workflows[-1] == exact_workflow.statements


def test_given_persistence_failure_when_executing_direct_build_then_warehouse_is_untouched(
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=("beta",),
    )
    connection: RecordingDirectBuildConnection = RecordingDirectBuildConnection()
    workflow: DirectBuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=connection,
        snapshot=build_direct_execution_snapshot(),
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )

    with pytest.raises(RuntimeError, match="statement persistence failed"):
        _ = execute_direct_build_workflow(
            workflow=workflow,
            connection=connection,
            emitter=FailingPreparationEmitter(),
        )

    assert connection.workflow_mutation_statements == []


@pytest.mark.parametrize(
    "test_case",
    [
        DirectDistinctCaptureTestCase(
            description="each replay root consumes its own process-owned capture",
            expected_capture_models=("beta", "delta"),
            expected_replay_sql_fragments=("11 AS cutoff_offset", "21 AS cutoff_offset"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_distinct_root_captures_when_executing_then_each_replay_uses_matching_capture(
    test_case: DirectDistinctCaptureTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=("beta",),
    )
    connection: DistinctCaptureDirectBuildConnection = DistinctCaptureDirectBuildConnection()
    workflow: DirectBuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=connection,
        snapshot=build_direct_execution_snapshot(),
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )

    runtime_execution: DirectRuntimeExecution = execute_direct_build_workflow(
        workflow=workflow,
        connection=connection,
    )

    statements_by_id: dict[str, WarehouseStatement] = {
        statement.step_id: statement for statement in runtime_execution.workflow.statements
    }
    replay_sql: tuple[str, ...] = tuple(
        statements_by_id[f"replay_{model_name}"].sql
        for model_name in test_case.expected_capture_models
    )
    assert tuple(capture.logical_model_name for capture in runtime_execution.captures) == (
        test_case.expected_capture_models
    )
    assert tuple(
        fragment in sql
        for fragment, sql in zip(test_case.expected_replay_sql_fragments, replay_sql, strict=True)
    ) == (True, True)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectCaptureValidationTestCase(
            description="capture identity must match the replay root",
            expected_error_fragment="tbl__wrong_root' instead of 'tbl__alpha",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mismatched_capture_identity_when_executing_then_replay_fails_closed(
    test_case: DirectCaptureValidationTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=("beta",),
    )
    connection: MismatchedCaptureDirectBuildConnection = MismatchedCaptureDirectBuildConnection()
    workflow: DirectBuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=connection,
        snapshot=build_direct_execution_snapshot(),
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )

    with pytest.raises(DirectWorkflowExecutionError) as raised:
        execute_direct_build_workflow(workflow=workflow, connection=connection)

    assert isinstance(raised.value.cause, AdapterResultError)
    assert test_case.expected_error_fragment in str(raised.value.cause)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectCaptureValidationTestCase(
            description="offset capture must identify its partition",
            expected_error_fragment="offset boundary without a partition",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partitionless_offset_capture_when_executing_then_replay_fails_closed(
    test_case: DirectCaptureValidationTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=("beta",),
    )
    connection: InvalidOffsetCaptureDirectBuildConnection = (
        InvalidOffsetCaptureDirectBuildConnection()
    )
    workflow: DirectBuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=connection,
        snapshot=build_direct_execution_snapshot(),
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )

    with pytest.raises(DirectWorkflowExecutionError) as raised:
        execute_direct_build_workflow(workflow=workflow, connection=connection)

    assert isinstance(raised.value.cause, AdapterResultError)
    assert test_case.expected_error_fragment in str(raised.value.cause)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectFingerprintPersistenceTestCase(
            description="adapter rendering denial remains an optional fingerprint warning",
            expected_warning_fragment="injected fingerprint rendering denial",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_denied_fingerprint_rendering_when_persisting_then_warning_is_returned(
    test_case: DirectFingerprintPersistenceTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=("beta",),
    )
    connection: DeniedFingerprintRenderingConnection = DeniedFingerprintRenderingConnection()

    warning: str | None = persist_direct_fingerprints(request=request, connection=connection)

    assert warning is not None
    assert test_case.expected_warning_fragment in warning


@pytest.mark.parametrize(
    "test_case",
    [
        DirectFingerprintMetadataTestCase(
            description="records MODEL storage in the direct baseline",
            model_name="beta",
            expected_storage_key="storage",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_model_when_persisting_fingerprint_then_storage_identity_is_recorded(
    test_case: DirectFingerprintMetadataTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=(test_case.model_name,),
    )
    connection: RecordingFingerprintConnection = RecordingFingerprintConnection()

    warning: str | None = persist_direct_fingerprints(request=request, connection=connection)

    fingerprint_by_identity: dict[str, AdapterDirectFingerprintRecord] = {
        record.logical_model_identity: record for record in connection.fingerprints
    }
    model_by_name: dict[str, CompiledModel] = {
        model.key.name: model for model in request.realized_project.project.models
    }
    metadata: dict = json.loads(
        fingerprint_by_identity[f"analytics.{test_case.model_name}"].identity_metadata
    )
    assert warning is None
    assert metadata[test_case.expected_storage_key] == build_model_storage_identity(
        model_by_name[test_case.model_name]
    )
