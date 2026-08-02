from pathlib import Path

import pytest

from streambuild.cli.plan.main._render_direct_plan_json import render_direct_plan_json
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.executor.direct.main.assemble_direct_build_workflow import (
    assemble_direct_build_workflow,
)
from streambuild.executor.direct.models import DirectBuildRequest
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main.execute_build_workflow import execute_build_workflow
from streambuild.executor.workflow.models import (
    BuildWorkflow,
    PublishedBuildWorkflow,
    WarehouseStatement,
)
from streambuild.executor.workflow.types import WorkflowPhase
from tests.unit.src.streambuild.executor.direct.main._test_types import (
    DirectWorkflowDriftTestCase,
    DirectWorkflowTestCase,
)
from tests.unit.src.streambuild.executor.direct.main.helpers import (
    DriftingDirectBuildConnection,
    RecordingDirectBuildConnection,
    build_direct_execution_request,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectWorkflowTestCase(
            description="direct workflow publishes and executes exact ordered statement bytes",
            expected_first_phase=WorkflowPhase.PREFLIGHT,
            expected_last_phase=WorkflowPhase.FINALIZATION,
            expected_replay_count=2,
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
    workflow: BuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=connection,
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )
    published: PublishedBuildWorkflow = publish_build_workflow(
        target_dir=tmp_path / "target",
        workflow=workflow,
    )

    _ = execute_build_workflow(published_workflow=published, connection=connection)

    statements: tuple[WarehouseStatement, ...] = workflow.statements
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
    assert step_bytes == tuple(statement.sql for statement in statements)
    assert (published.artifact_root / "workflow.sql").read_text(encoding="utf-8") == (
        "\n".join(statement.sql for statement in statements)
    )
    assert set(connection.workflow_mutation_statements) <= set(all_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectWorkflowDriftTestCase(
            description="direct preflight drift aborts before the first warehouse mutation",
            expected_failed_step_id="assert_ownership_tbl__beta",
            expected_mutation_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_state_drift_when_executing_then_preflight_aborts_before_mutation(
    test_case: DirectWorkflowDriftTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_direct_execution_request(
        project_root=tmp_path,
        selected_model_names=("beta",),
    )
    connection: DriftingDirectBuildConnection = DriftingDirectBuildConnection()
    workflow: BuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=connection,
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )
    published: PublishedBuildWorkflow = publish_build_workflow(
        target_dir=tmp_path / "target",
        workflow=workflow,
    )
    connection.reject_preflight()

    with pytest.raises(WorkflowExecutionError) as error_info:
        execute_build_workflow(published_workflow=published, connection=connection)

    assert error_info.value.failed_step_id == test_case.expected_failed_step_id
    assert len(connection.workflow_mutation_statements) == test_case.expected_mutation_count
