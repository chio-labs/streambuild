from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from tests.unit.src.streambuild.cli.build.main._test_types import CliBuildGateTestCase
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
            description="a virtual-environment project cannot be built in direct mode",
            virtual_environments=True,
            json_output=False,
            auto_approve=True,
            confirmation_response="y",
            expected_exit_code=1,
            expected_stderr_fragment="stb build is a direct-mode command",
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
