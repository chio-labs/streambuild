import json
from pathlib import Path

import pytest

from streambuild.cli.plan.constants import DIRECT_MODE_LABEL, VIRTUAL_ENVIRONMENTS_MODE_LABEL
from streambuild.cli.workflow_artifacts.main._publish_plan_workflow import publish_plan_workflow
from streambuild.executor.workflow.models import BuildWorkflow
from streambuild.executor.workflow.types import WorkflowMode
from tests.unit.src.streambuild.cli.plan.main._test_types import (
    CliDirectPlanFlagRejectionTestCase,
    CliPlanDeploymentIdRejectionTestCase,
    CliPlanModeRoutingTestCase,
    CliPlanPublicationFailureTestCase,
)
from tests.unit.src.streambuild.cli.plan.main.helpers import (
    fail_second_workflow_artifact_replace,
    run_scope_project_plan,
)
from tests.unit.src.streambuild.compiler.planner.helpers import write_direct_scope_project


@pytest.mark.parametrize(
    "test_case",
    [
        CliPlanModeRoutingTestCase(
            description="an omitted virtual_environments setting plans in direct mode",
            virtual_environments=None,
            expected_mode=DIRECT_MODE_LABEL,
            expected_title="Direct plan",
        ),
        CliPlanModeRoutingTestCase(
            description="a disabled virtual_environments setting plans in direct mode",
            virtual_environments=False,
            expected_mode=DIRECT_MODE_LABEL,
            expected_title="Direct plan",
        ),
        CliPlanModeRoutingTestCase(
            description="an enabled virtual_environments setting preserves deployment planning",
            virtual_environments=True,
            expected_mode=VIRTUAL_ENVIRONMENTS_MODE_LABEL,
            expected_title="Plan Ready",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_effective_project_mode_when_planning_then_that_mode_is_used(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], test_case: CliPlanModeRoutingTestCase
) -> None:
    write_direct_scope_project(
        project_root=tmp_path, virtual_environments=test_case.virtual_environments
    )
    virtual_environments: bool = test_case.virtual_environments is True
    deployment_id: str | None = {
        False: None,
        True: "20260802T120000Z_planmode",
    }[virtual_environments]

    text_exit_code: int = run_scope_project_plan(
        project_root=tmp_path,
        json_output=False,
        virtual_environments=virtual_environments,
        deployment_id=deployment_id,
    )
    text_output: str = capsys.readouterr().out
    artifact_path: Path = tmp_path / test_case.expected_artifact_path
    text_artifact: bytes = artifact_path.read_bytes()
    json_exit_code: int = run_scope_project_plan(
        project_root=tmp_path,
        json_output=True,
        virtual_environments=virtual_environments,
        deployment_id=deployment_id,
    )
    json_output: str = capsys.readouterr().out
    payload: dict[str, object] = json.loads(json_output)

    assert (text_exit_code, json_exit_code) == (0, 0)
    assert test_case.expected_title in text_output
    assert payload["mode"] == test_case.expected_mode
    assert payload["adapter"] == "clickhouse"
    assert json.loads(text_artifact) == payload
    assert artifact_path.read_bytes() == json_output.encode("utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        CliPlanModeRoutingTestCase(
            description="direct mode reports the complete closure and its single replay root",
            virtual_environments=None,
            expected_mode=DIRECT_MODE_LABEL,
            expected_title="Direct Plan",
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_replay_root_models=("alpha",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_mode_when_planning_then_full_closure_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], test_case: CliPlanModeRoutingTestCase
) -> None:
    write_direct_scope_project(
        project_root=tmp_path, virtual_environments=test_case.virtual_environments
    )

    exit_code: int = run_scope_project_plan(project_root=tmp_path, json_output=True)

    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert tuple(key["name"] for key in payload["execution_scope"]) == (
        test_case.expected_execution_scope
    )
    assert payload["database"] == "analytics"
    assert (
        tuple(root["model_key"]["name"] for root in payload["replay_roots"])
        == test_case.expected_replay_root_models
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CliPlanDeploymentIdRejectionTestCase(
            description="deployment identity is rejected in direct mode",
            deployment_id="20260802T120000Z_directinvalid",
            expected_error_fragment="--deployment-id requires virtual environments",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deployment_id_in_direct_mode_when_planning_then_command_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: CliPlanDeploymentIdRejectionTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path)

    exit_code: int = run_scope_project_plan(
        project_root=tmp_path,
        json_output=False,
        deployment_id=test_case.deployment_id,
    )

    assert exit_code == 1
    assert test_case.expected_error_fragment in capsys.readouterr().err
    assert not (tmp_path / "target/run/plan").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectPlanFlagRejectionTestCase(
            description="--full-refresh is rejected in direct mode",
            selectors=("alpha",),
            full_refresh=True,
            start_time=None,
            expected_error_fragment="--full-refresh is a virtual-environment replay control",
            expected_preserved_artifact=b'{"previous":"plan"}\n',
        ),
        CliDirectPlanFlagRejectionTestCase(
            description="--start-time without selection is rejected before inspection",
            selectors=(),
            full_refresh=False,
            start_time="2026-01-01",
            expected_error_fragment="--start-time requires at least one --select",
            expected_preserved_artifact=b'{"previous":"plan"}\n',
        ),
        CliDirectPlanFlagRejectionTestCase(
            description="--start-time and --full-refresh remain mutually exclusive",
            selectors=("alpha",),
            full_refresh=True,
            start_time="2026-01-01",
            expected_error_fragment="--full-refresh cannot be combined with --start-time",
            expected_preserved_artifact=b'{"previous":"plan"}\n',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_full_refresh_in_direct_mode_when_planning_then_command_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: CliDirectPlanFlagRejectionTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path)
    artifact_path: Path = tmp_path / "target/run/plan/plan.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(test_case.expected_preserved_artifact)

    exit_code: int = run_scope_project_plan(
        project_root=tmp_path,
        json_output=False,
        selectors=test_case.selectors,
        full_refresh=test_case.full_refresh,
        start_time=test_case.start_time,
    )

    assert exit_code == 1
    assert test_case.expected_error_fragment in capsys.readouterr().err
    assert artifact_path.read_bytes() == test_case.expected_preserved_artifact


@pytest.mark.parametrize(
    "test_case",
    [
        CliPlanPublicationFailureTestCase(
            description="a failed atomic replacement preserves the previous complete plan",
            previous_artifact=b'{"previous":"plan"}\n',
            replacement_artifact='{"replacement":"plan"}\n',
            expected_error_fragment="publication failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_plan_when_atomic_publication_fails_then_preserves_previous_artifact(
    test_case: CliPlanPublicationFailureTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path: Path = tmp_path / "run/plan/plan.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(test_case.previous_artifact)
    fail_second_workflow_artifact_replace(
        monkeypatch=monkeypatch,
        error_message=test_case.expected_error_fragment,
    )

    with pytest.raises(OSError, match=test_case.expected_error_fragment):
        publish_plan_workflow(
            target_dir=tmp_path,
            workflow=BuildWorkflow(
                mode=WorkflowMode.DIRECT,
                plan_json=test_case.replacement_artifact,
                statements=(),
            ),
        )

    assert artifact_path.read_bytes() == test_case.previous_artifact
    assert tuple(artifact_path.parent.iterdir()) == (artifact_path,)
