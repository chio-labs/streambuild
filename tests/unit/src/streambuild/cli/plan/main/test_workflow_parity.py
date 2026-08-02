from pathlib import Path

import pytest

from tests.unit.src.streambuild.cli.build.main.helpers import (
    run_scope_project_build,
    run_scope_project_virtual_build,
)
from tests.unit.src.streambuild.cli.plan.main._test_types import (
    CliDirectWorkflowParityTestCase,
    CliVirtualWorkflowParityTestCase,
)
from tests.unit.src.streambuild.cli.plan.main.helpers import (
    read_workflow_artifact,
    run_scope_project_plan,
)
from tests.unit.src.streambuild.compiler.planner.helpers import write_direct_scope_project


@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectWorkflowParityTestCase(
            description="direct plan and build publish identical disposable workflows",
            expected_removed_step_name="9999_stale.sql",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_direct_state_when_planning_and_building_then_workflow_bytes_match(
    tmp_path: Path,
    test_case: CliDirectWorkflowParityTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path)
    stale_root: Path = tmp_path / "target/run/plan"
    stale_steps_root: Path = stale_root / "steps"
    stale_steps_root.mkdir(parents=True)
    (stale_root / "plan.json").write_text("not json", encoding="utf-8")
    (stale_root / "workflow.sql").write_text("not sql", encoding="utf-8")
    (stale_steps_root / test_case.expected_removed_step_name).write_text(
        "not sql", encoding="utf-8"
    )

    plan_exit_code: int = run_scope_project_plan(project_root=tmp_path, json_output=True)
    plan_artifact: tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]] = read_workflow_artifact(
        artifact_root=tmp_path / "target/run/plan"
    )
    build_exit_code: int = run_scope_project_build(
        project_root=tmp_path,
        json_output=True,
        auto_approve=True,
    )
    build_artifact: tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]] = (
        read_workflow_artifact(artifact_root=tmp_path / "target/run/build")
    )

    assert (plan_exit_code, build_exit_code) == (0, 0)
    assert plan_artifact == build_artifact
    assert plan_artifact[0].endswith(b"\n")
    assert plan_artifact[1] == b"\n".join(plan_artifact[3])
    assert plan_artifact[2]
    assert test_case.expected_removed_step_name not in plan_artifact[2]


@pytest.mark.parametrize(
    "test_case",
    [
        CliVirtualWorkflowParityTestCase(
            description="virtual plan and build publish identical fixed-identity workflows",
            deployment_id="20260802T120000Z_planbuildparity",
            expected_removed_step_name="9999_stale.sql",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_virtual_identity_when_planning_and_building_then_workflow_bytes_match(
    tmp_path: Path,
    test_case: CliVirtualWorkflowParityTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path, virtual_environments=True)

    plan_exit_code: int = run_scope_project_plan(
        project_root=tmp_path,
        json_output=True,
        virtual_environments=True,
        deployment_id=test_case.deployment_id,
    )
    plan_artifact: tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]] = read_workflow_artifact(
        artifact_root=tmp_path / "target/run/plan"
    )
    stale_build_root: Path = tmp_path / "target/run/build"
    stale_build_steps_root: Path = stale_build_root / "steps"
    stale_build_steps_root.mkdir(parents=True)
    (stale_build_root / "plan.json").write_text("not json", encoding="utf-8")
    (stale_build_root / "workflow.sql").write_text("not sql", encoding="utf-8")
    (stale_build_steps_root / test_case.expected_removed_step_name).write_text(
        "not sql", encoding="utf-8"
    )
    build_exit_code: int = run_scope_project_virtual_build(
        project_root=tmp_path,
        deployment_id=test_case.deployment_id,
    )
    build_artifact: tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]] = (
        read_workflow_artifact(artifact_root=tmp_path / "target/run/build")
    )

    assert (plan_exit_code, build_exit_code) == (0, 0)
    assert plan_artifact == build_artifact
    assert plan_artifact[0].endswith(b"\n")
    assert plan_artifact[1] == b"\n".join(plan_artifact[3])
    assert plan_artifact[2]
    assert test_case.expected_removed_step_name not in build_artifact[2]
