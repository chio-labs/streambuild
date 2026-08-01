import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from tests.unit.src.streambuild.cli.build.main._test_types import (
    CliBuildArtifactTestCase,
    CliBuildGateTestCase,
)
from tests.unit.src.streambuild.cli.build.main.helpers import run_scope_project_build
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

    exit_code: int = run_scope_project_build(
        project_root=tmp_path,
        json_output=test_case.json_output,
        auto_approve=test_case.auto_approve,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in captured.err
    assert test_case.expected_stdout_fragment in captured.out
    assert not (tmp_path / "target/run/build/plan.json").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        CliBuildArtifactTestCase(
            description="an approved direct build publishes its plan before execution",
            expected_exit_code=1,
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
