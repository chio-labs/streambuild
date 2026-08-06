from pathlib import Path

import pytest

from streambuild.cli.plan.main._render_direct_plan_json import render_direct_plan_json
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.executor.direct.main.assemble_direct_build_workflow import (
    assemble_direct_build_workflow,
)
from streambuild.executor.direct.models import DirectBuildRequest
from streambuild.executor.workflow.main.execute_build_workflow import execute_build_workflow
from streambuild.executor.workflow.models import (
    BuildWorkflow,
    PublishedBuildWorkflow,
    WarehouseStatement,
)
from streambuild.executor.workflow.types import WorkflowPhase
from tests.unit.src.streambuild.executor.direct.main._test_types import DirectWorkflowTestCase
from tests.unit.src.streambuild.executor.direct.main.helpers import (
    RecordingDirectBuildConnection,
    build_direct_execution_request,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectWorkflowTestCase(
            description="direct workflow publishes and executes exact ordered statement bytes",
            expected_first_phase=WorkflowPhase.PREPARATION,
            expected_last_phase=WorkflowPhase.FINALIZATION,
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
    step_ids: tuple[str, ...] = tuple(statement.step_id for statement in statements)
    boundary_windows: tuple[tuple[str, ...], ...] = tuple(
        step_ids[
            step_ids.index(f"read_boundary_{model_segment}") - 1 : step_ids.index(
                f"read_boundary_{model_segment}"
            )
            + 2
        ]
        for model_segment in test_case.expected_boundary_model_segments
    )
    expected_boundary_windows: tuple[tuple[str, ...], ...] = tuple(
        (
            f"refresh_boundary_{model_segment}_checkpoint",
            f"read_boundary_{model_segment}",
            f"replay_{model_segment}",
        )
        for model_segment in test_case.expected_boundary_model_segments
    )
    assert boundary_windows == expected_boundary_windows
    assert step_bytes == tuple(statement.sql for statement in statements)
    assert (published.artifact_root / "workflow.sql").read_text(encoding="utf-8") == (
        "\n".join(statement.sql for statement in statements)
    )
    assert set(connection.workflow_mutation_statements) <= set(all_sql)
