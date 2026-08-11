import json
import re
from pathlib import Path
from typing import cast

import pytest
from _pytest.capture import CaptureResult

from streambuild.executor.backfill.models import BackfillDeploymentIdentity
from streambuild.executor.observability.constants import RUN_INVOCATION_ID_ENV_VAR
from streambuild.executor.workflow.models import PublishedBuildWorkflow
from tests.unit.src.streambuild.cli.build.main._test_types import (
    CliAllowedPipelineLimitTestCase,
    CliBuildArtifactTestCase,
    CliBuildGateTestCase,
    CliBuildInterruptTestCase,
    CliMixedBuildTestCase,
    CliProtectedBuildTestCase,
    CliRejectedPipelineLimitTestCase,
    CliRunScopeTestCase,
    CliVirtualBuildArtifactTestCase,
)
from tests.unit.src.streambuild.cli.build.main.helpers import (
    InterruptedBuildConnection,
    build_interrupted_scope_project_connection,
    build_mixed_scope_project_connection,
    build_scope_project_connection,
    publish_scope_project_virtual_workflow,
    run_scope_project_build,
    run_scope_project_build_with_connection,
    run_scope_project_virtual_build,
    write_mixed_scope_project,
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
        CliProtectedBuildTestCase(
            description="auto-approved protected build requires the exact confirmation",
            warning="Interrupts protected order processing.",
            confirmation="DEPLOY_ORDERS",
            expected_rejected_exit_code=1,
            expected_accepted_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_protected_pipeline_when_auto_approving_then_requires_exact_confirmation(
    test_case: CliProtectedBuildTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_direct_scope_project(project_root=tmp_path)
    (tmp_path / "pipelines" / "pl__orders" / "pipeline.toml").write_text(
        f"""
[protection]
warning = "{test_case.warning}"
confirmation = "{test_case.confirmation}"
""".strip(),
        encoding="utf-8",
    )
    rejected_connection: RecordingAdapterConnection = build_scope_project_connection()

    rejected_exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=False,
        auto_approve=True,
        connection=rejected_connection,
    )

    assert rejected_exit_code == test_case.expected_rejected_exit_code
    assert rejected_connection.workflow_mutation_statements == []
    assert f"--confirm {test_case.confirmation}" in capsys.readouterr().err

    accepted_exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=False,
        auto_approve=True,
        connection=build_scope_project_connection(),
        confirmations=(test_case.confirmation,),
    )

    assert accepted_exit_code == test_case.expected_accepted_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        CliBuildInterruptTestCase(
            description="a Ctrl+C during execution persists a cancelled invocation",
            expected_exit_code=130,
            expected_invocation_outcome="cancelled",
            expected_stderr_fragment="Cancelled  Build interrupted and recorded as cancelled.",
            expected_execution_status="cancelled",
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
    execution_payload: dict[str, object] = json.loads(
        (tmp_path / "target/run/build/execution.json").read_text(encoding="utf-8")
    )
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in captured.err
    assert connection.invocation_observations[0].outcome == test_case.expected_invocation_outcome
    assert execution_payload["status"] == test_case.expected_execution_status


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


@pytest.mark.parametrize(
    "test_case",
    [
        CliMixedBuildTestCase(
            description="runs virtual staging before direct application",
            expected_exit_code=0,
            expected_mode="mixed",
            expected_execution_order=("virtual", "direct"),
            expected_virtual_phase_fragment="Phase 1/2  VIRTUAL",
            expected_direct_phase_fragment="Phase 2/2  DIRECT",
            expected_completion_fragment=("Direct changes are live. Virtual changes remain staged"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_pipeline_modes_when_building_then_virtual_runs_before_direct(
    test_case: CliMixedBuildTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_mixed_scope_project(project_root=tmp_path)
    connection: RecordingAdapterConnection = build_mixed_scope_project_connection()
    monkeypatch.setattr(
        "streambuild.cli.build._helpers.virtual_command.reset_fresh_landing_offsets",
        lambda **_kwargs: (),
    )

    exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=False,
        auto_approve=True,
        connection=connection,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    output: str = captured.out
    assert exit_code == test_case.expected_exit_code, captured
    assert "Mixed Build Plan" in output
    assert output.index(test_case.expected_virtual_phase_fragment) < output.index(
        test_case.expected_direct_phase_fragment
    )
    assert test_case.expected_completion_fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        CliRejectedPipelineLimitTestCase(
            description="target limit rejects a mixed build before mutation",
            project_max_pipelines=2,
            target_max_pipelines=1,
            expected_exit_code=1,
            expected_error_fragment="Build affects 2 pipelines, exceeding max_pipelines=1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_exceeded_pipeline_limit_when_running_then_rejects_before_mutation(
    test_case: CliRejectedPipelineLimitTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_mixed_scope_project(project_root=tmp_path)
    project_path: Path = tmp_path / "streambuild_project.toml"
    project_path.write_text(
        project_path.read_text(encoding="utf-8")
        + f"\n[build]\nmax_pipelines = {test_case.project_max_pipelines}\n"
        + f"\n[targets.test.build]\nmax_pipelines = {test_case.target_max_pipelines}\n",
        encoding="utf-8",
    )
    connection: RecordingAdapterConnection = build_mixed_scope_project_connection()

    exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=False,
        auto_approve=True,
        connection=connection,
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    assert test_case.expected_error_fragment in captured.err
    assert connection.statements == []
    assert connection.workflow_mutation_statements == []
    assert connection.invocation_observations == []
    assert not (tmp_path / "target/run/build").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        CliAllowedPipelineLimitTestCase(
            description="selection within the project limit proceeds",
            project_max_pipelines=1,
            selectors=("alpha",),
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selection_within_pipeline_limit_when_running_then_build_proceeds(
    test_case: CliAllowedPipelineLimitTestCase,
    tmp_path: Path,
) -> None:
    write_mixed_scope_project(project_root=tmp_path)
    project_path: Path = tmp_path / "streambuild_project.toml"
    project_path.write_text(
        project_path.read_text(encoding="utf-8")
        + f"\n[build]\nmax_pipelines = {test_case.project_max_pipelines}\n",
        encoding="utf-8",
    )

    exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=False,
        auto_approve=True,
        connection=build_mixed_scope_project_connection(),
        selectors=test_case.selectors,
    )

    assert exit_code == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        CliRunScopeTestCase(
            description="records each mixed phase from its own confirmed plan",
            parent_invocation_id="parent-assigned-invocation",
            expected_executed_logical_ids=(
                ("model:virtual_alpha",),
                ("model:alpha", "model:beta", "model:gamma", "model:delta"),
            ),
            expected_context_logical_ids=(("source:orders",), ("source:orders",)),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_pipeline_modes_when_emitting_events_then_each_phase_has_exact_plan_scope(
    test_case: CliRunScopeTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_mixed_scope_project(project_root=tmp_path)
    monkeypatch.setattr(
        "streambuild.cli.build._helpers.virtual_command.reset_fresh_landing_offsets",
        lambda **_kwargs: (),
    )
    monkeypatch.setenv(RUN_INVOCATION_ID_ENV_VAR, test_case.parent_invocation_id)

    exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=False,
        auto_approve=True,
        connection=build_mixed_scope_project_connection(),
        events_output=True,
    )

    started_events: list[dict[str, object]] = [
        json.loads(line)
        for line in re.findall(
            r'^\{"event": "run_started".*$', capsys.readouterr().out, re.MULTILINE
        )
    ]
    assert exit_code == 0
    assert started_events[0]["invocationId"] == test_case.parent_invocation_id
    assert started_events[1]["invocationId"] != test_case.parent_invocation_id
    assert (
        tuple(tuple(cast(list[str], event["executedLogicalIds"])) for event in started_events)
        == test_case.expected_executed_logical_ids
    )
    assert (
        tuple(tuple(cast(list[str], event["contextLogicalIds"])) for event in started_events)
        == test_case.expected_context_logical_ids
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CliMixedBuildTestCase(
            description="emits one mixed JSON document",
            expected_exit_code=0,
            expected_mode="mixed",
            expected_execution_order=("virtual", "direct"),
            expected_virtual_phase_fragment="virtual",
            expected_direct_phase_fragment="direct",
            expected_completion_fragment="mode",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_pipeline_modes_when_building_json_then_it_emits_one_document(
    test_case: CliMixedBuildTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_mixed_scope_project(project_root=tmp_path)
    monkeypatch.setattr(
        "streambuild.cli.build._helpers.virtual_command.reset_fresh_landing_offsets",
        lambda **_kwargs: (),
    )

    exit_code: int = run_scope_project_build_with_connection(
        project_root=tmp_path,
        json_output=True,
        auto_approve=True,
        connection=build_mixed_scope_project_connection(),
    )

    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert exit_code == test_case.expected_exit_code
    assert payload[test_case.expected_completion_fragment] == test_case.expected_mode
    assert payload["execution_order"] == list(test_case.expected_execution_order)
    assert isinstance(payload[test_case.expected_virtual_phase_fragment], dict)
    assert isinstance(payload[test_case.expected_direct_phase_fragment], dict)
