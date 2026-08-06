import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from streambuild.executor.backfill.models import BackfillDeploymentIdentity
from streambuild.executor.workflow.models import PublishedBuildWorkflow
from tests.unit.src.streambuild.cli.build.main._test_types import (
    CliBuildArtifactTestCase,
    CliBuildGateTestCase,
    CliBuildInterruptTestCase,
    CliVirtualBuildArtifactTestCase,
)
from tests.unit.src.streambuild.cli.build.main.helpers import (
    InterruptedBuildConnection,
    build_interrupted_scope_project_connection,
    build_scope_project_connection,
    publish_scope_project_virtual_workflow,
    run_scope_project_build,
    run_scope_project_build_with_connection,
    run_scope_project_virtual_build,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.compiler.planner.helpers import write_direct_scope_project


@pytest.mark.parametrize(
    "test_case",
    [
        CliBuildGateTestCase(
            description="json output requires auto approve",
            virtual_environments=None,
            json_output=True,
            auto_approve=False,
            confirmation_response="y",
            expected_exit_code=1,
            expected_stderr_fragment="--json requires --auto-approve for build",
            expected_stdout_fragment="",
            expected_invocation_outcome="failed",
        ),
        CliBuildGateTestCase(
            description="a declined confirmation cancels before any warehouse write",
            virtual_environments=None,
            json_output=False,
            auto_approve=False,
            confirmation_response="n",
            expected_exit_code=1,
            expected_stderr_fragment="",
            expected_stdout_fragment="Build cancelled.",
            expected_invocation_outcome="cancelled",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_build_command_gates_when_running_then_it_refuses_before_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_case: CliBuildGateTestCase,
) -> None:
    write_direct_scope_project(
        project_root=tmp_path, virtual_environments=test_case.virtual_environments
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: test_case.confirmation_response)
    connection: RecordingAdapterConnection = build_scope_project_connection()

    exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=test_case.json_output,
        auto_approve=test_case.auto_approve,
        connection=connection,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in captured.err
    assert test_case.expected_stdout_fragment in captured.out
    assert not (tmp_path / "target/run/build/plan.json").exists()
    assert connection.workflow_mutation_statements == []
    assert connection.invocation_observations[0].outcome == test_case.expected_invocation_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        CliBuildInterruptTestCase(
            description="a Ctrl+C during execution persists a cancelled invocation",
            expected_exit_code=130,
            expected_invocation_outcome="cancelled",
            expected_stderr_fragment="build interrupted; recorded as cancelled",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_execution_when_building_then_cancelled_invocation_is_recorded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: CliBuildInterruptTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path)
    connection: InterruptedBuildConnection = build_interrupted_scope_project_connection()

    exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=False,
        auto_approve=True,
        connection=connection,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in captured.err
    assert connection.invocation_observations[0].outcome == test_case.expected_invocation_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        CliBuildArtifactTestCase(
            description="an approved direct build publishes its plan before execution",
            expected_exit_code=0,
            expected_mode="direct",
            expected_adapter="clickhouse",
            expected_artifact_path="target/run/build/plan.json",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_approved_direct_build_when_running_then_connected_plan_is_published(
    tmp_path: Path,
    test_case: CliBuildArtifactTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path)

    exit_code: int = run_scope_project_build(
        project_root=tmp_path,
        json_output=True,
        auto_approve=True,
    )

    artifact_payload: dict[str, object] = json.loads(
        (tmp_path / test_case.expected_artifact_path).read_text(encoding="utf-8")
    )
    assert exit_code == test_case.expected_exit_code
    assert artifact_payload["mode"] == test_case.expected_mode
    assert artifact_payload["adapter"] == test_case.expected_adapter


@pytest.mark.parametrize(
    "test_case",
    [
        CliVirtualBuildArtifactTestCase(
            description=(
                "virtual artifacts retain one fixed deployment identity and exact step bytes"
            ),
            deployment_id="20260801T120000Z_virtualartifact",
            expected_created_at="2026-08-01 12:00:00.000",
            expected_mode="virtual environments",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fixed_virtual_identity_when_publishing_then_plan_and_steps_are_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: CliVirtualBuildArtifactTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path, virtual_environments=True)
    monkeypatch.setattr(
        "streambuild.cli.build._helpers.virtual_preview.build_backfill_deployment_identity",
        lambda *, deployment_id: BackfillDeploymentIdentity(
            deployment_id=deployment_id,
            created_at=test_case.expected_created_at,
        ),
    )

    exit_code: int = run_scope_project_virtual_build(
        project_root=tmp_path,
        deployment_id=test_case.deployment_id,
    )
    plan_payload: dict[str, object] = json.loads(
        (tmp_path / "target/run/build/plan.json").read_text(encoding="utf-8")
    )
    published: PublishedBuildWorkflow = publish_scope_project_virtual_workflow(
        project_root=tmp_path,
        deployment_id=test_case.deployment_id,
    )
    step_paths: tuple[Path, ...] = tuple(sorted((published.artifact_root / "steps").iterdir()))
    assert exit_code == test_case.expected_exit_code
    assert plan_payload["mode"] == test_case.expected_mode
    assert plan_payload["deployment_id"] == test_case.deployment_id
    assert plan_payload["deployment_created_at"] == test_case.expected_created_at
    assert tuple(path.read_bytes() for path in step_paths) == tuple(
        statement.sql.encode("utf-8") for statement in published.workflow.statements
    )
